"""Data-quality gates for every stage of the pipeline.

Philosophy: a delivery that fails loudly at the QA gate is cheap; a wrong
delivery that reaches a grid operator is expensive. Every check returns a
structured :class:`CheckResult` (never a bare log line), so results can be
rendered into a QA report, asserted in tests, and root-caused later.

Severity semantics:
- ``error`` — delivery-blocking; the pipeline aborts (unless overridden).
- ``warning`` — delivery proceeds, but the report flags it for review.
- ``info`` — context recorded for traceability (e.g. pixel counts).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class CheckResult:
    check: str
    passed: bool
    severity: Severity
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
        }


class QAGateError(RuntimeError):
    """Raised when delivery-blocking checks fail."""


# ---------------------------------------------------------------------------
# Raster checks
# ---------------------------------------------------------------------------

def run_raster_checks(
    path: str,
    label: str,
    expected_crs: str,
    valid_range: tuple[float, float],
    max_nodata_fraction: float,
) -> list[CheckResult]:
    """Validate a single-band analysis raster (NDVI / dNDVI)."""
    results: list[CheckResult] = []
    with rasterio.open(path) as src:
        arr = src.read(1)

        # CRS
        crs_ok = str(src.crs) == expected_crs
        results.append(
            CheckResult(
                check=f"{label}: CRS matches AOI grid",
                passed=crs_ok,
                severity=Severity.ERROR,
                message=f"raster CRS {src.crs} vs expected {expected_crs}",
                details={"crs": str(src.crs)},
            )
        )

        # NoData / NaN fraction
        finite = np.isfinite(arr)
        nodata_fraction = float(1.0 - finite.mean())
        results.append(
            CheckResult(
                check=f"{label}: nodata fraction <= {max_nodata_fraction:.0%}",
                passed=nodata_fraction <= max_nodata_fraction,
                severity=Severity.ERROR,
                message=f"nodata fraction = {nodata_fraction:.2%}",
                details={"nodata_fraction": round(nodata_fraction, 4)},
            )
        )

        # Value range on valid pixels
        if finite.any():
            vmin, vmax = float(arr[finite].min()), float(arr[finite].max())
            in_range = vmin >= valid_range[0] - 1e-6 and vmax <= valid_range[1] + 1e-6
            results.append(
                CheckResult(
                    check=f"{label}: values within {valid_range}",
                    passed=in_range,
                    severity=Severity.ERROR,
                    message=f"observed range [{vmin:.3f}, {vmax:.3f}]",
                    details={"min": round(vmin, 4), "max": round(vmax, 4)},
                )
            )

            # Degenerate raster (all-constant) — classic upstream-pipeline symptom
            std = float(arr[finite].std())
            results.append(
                CheckResult(
                    check=f"{label}: non-degenerate variance",
                    passed=std > 1e-6,
                    severity=Severity.WARNING,
                    message=f"std = {std:.5f} (a constant raster usually means a broken upstream read)",
                    details={"std": round(std, 6)},
                )
            )

        results.append(
            CheckResult(
                check=f"{label}: grid summary",
                passed=True,
                severity=Severity.INFO,
                message=f"{src.width}x{src.height} px @ {src.res[0]:.1f} m",
                details={"width": src.width, "height": src.height, "res_m": src.res[0]},
            )
        )
    return results


# ---------------------------------------------------------------------------
# Vector checks
# ---------------------------------------------------------------------------

def run_vector_checks(
    gdf: gpd.GeoDataFrame,
    label: str,
    expected_crs: str | None = None,
    min_features: int = 1,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    results.append(
        CheckResult(
            check=f"{label}: at least {min_features} feature(s)",
            passed=len(gdf) >= min_features,
            severity=Severity.ERROR,
            message=f"{len(gdf)} feature(s) present",
            details={"count": len(gdf)},
        )
    )

    if expected_crs is not None:
        results.append(
            CheckResult(
                check=f"{label}: CRS matches expected",
                passed=str(gdf.crs) == expected_crs,
                severity=Severity.ERROR,
                message=f"vector CRS {gdf.crs} vs expected {expected_crs}",
                details={"crs": str(gdf.crs)},
            )
        )

    invalid = int((~gdf.geometry.is_valid).sum()) if len(gdf) else 0
    empty = int(gdf.geometry.is_empty.sum()) if len(gdf) else 0
    results.append(
        CheckResult(
            check=f"{label}: geometries valid and non-empty",
            passed=invalid == 0 and empty == 0,
            severity=Severity.ERROR,
            message=f"{invalid} invalid, {empty} empty geometries",
            details={"invalid": invalid, "empty": empty},
        )
    )
    return results


# ---------------------------------------------------------------------------
# Output checks
# ---------------------------------------------------------------------------

def run_output_checks(scored: gpd.GeoDataFrame, min_segments: int) -> list[CheckResult]:
    """Sanity gates on the final risk table before it becomes a delivery."""
    results: list[CheckResult] = []

    results.append(
        CheckResult(
            check=f"delivery: >= {min_segments} scored segments",
            passed=len(scored) >= min_segments,
            severity=Severity.ERROR,
            message=f"{len(scored)} segments scored",
            details={"count": len(scored)},
        )
    )

    if "risk_score" in scored.columns and len(scored):
        smin, smax = float(scored["risk_score"].min()), float(scored["risk_score"].max())
        results.append(
            CheckResult(
                check="delivery: risk scores within [0, 1]",
                passed=0.0 <= smin and smax <= 1.0,
                severity=Severity.ERROR,
                message=f"score range [{smin:.3f}, {smax:.3f}]",
                details={"min": smin, "max": smax},
            )
        )

        nodata_segments = int((scored["risk_class"] == "no-data").sum())
        frac = nodata_segments / len(scored)
        results.append(
            CheckResult(
                check="delivery: no-data segments <= 20%",
                passed=frac <= 0.20,
                severity=Severity.WARNING,
                message=f"{nodata_segments} segment(s) ({frac:.0%}) had no valid pixels",
                details={"no_data_segments": nodata_segments},
            )
        )

        dist = scored["risk_class"].value_counts().to_dict()
        results.append(
            CheckResult(
                check="delivery: risk class distribution",
                passed=True,
                severity=Severity.INFO,
                message=", ".join(f"{k}={v}" for k, v in sorted(dist.items())),
                details=dist,
            )
        )
    return results


def gate(results: list[CheckResult], fail_on: tuple[str, ...] = ("error",)) -> None:
    """Abort the pipeline if any failed check has a blocking severity."""
    blocking = [
        r for r in results if not r.passed and r.severity.value in fail_on
    ]
    if blocking:
        lines = "\n".join(f"  - [{r.severity.value.upper()}] {r.check}: {r.message}" for r in blocking)
        raise QAGateError(f"QA gate failed — delivery blocked:\n{lines}")
