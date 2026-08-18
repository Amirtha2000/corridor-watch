"""Typed configuration loading.

A single YAML file drives a run so that every parameter that affects the
result (thresholds, buffer widths, date ranges) is versioned and reviewable —
no magic numbers buried in code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Config:
    """Immutable view over the run configuration."""

    raw: dict[str, Any] = field(repr=False)
    source_path: Path | None = None

    # --- convenience accessors -------------------------------------------------
    @property
    def bbox(self) -> list[float]:
        return list(self.raw["aoi"]["bbox"])

    @property
    def crs_utm(self) -> str:
        return self.raw["aoi"]["crs_utm"]

    @property
    def buffer_m(self) -> float:
        return float(self.raw["analysis"]["corridor_buffer_m"])

    @property
    def segment_length_m(self) -> float:
        return float(self.raw["analysis"]["segment_length_m"])

    @property
    def veg_threshold(self) -> float:
        return float(self.raw["analysis"]["ndvi_veg_threshold"])

    @property
    def growth_threshold(self) -> float:
        return float(self.raw["analysis"]["growth_dndvi_threshold"])

    @property
    def risk_weights(self) -> dict[str, float]:
        return dict(self.raw["risk"]["weights"])

    @property
    def risk_thresholds(self) -> dict[str, float]:
        return dict(self.raw["risk"]["thresholds"])

    @property
    def qa(self) -> dict[str, Any]:
        return dict(self.raw["qa"])

    def path(self, key: str) -> Path:
        base = self.source_path.parent.parent if self.source_path else Path.cwd()
        return base / self.raw["paths"][key]


def load_config(path: str | Path) -> Config:
    p = Path(path)
    with open(p) as fh:
        raw = yaml.safe_load(fh)
    _validate(raw)
    return Config(raw=raw, source_path=p.resolve())


def _validate(raw: dict[str, Any]) -> None:
    """Fail fast on malformed configuration — before any data is touched."""
    required = ["aoi", "analysis", "risk", "qa", "paths"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(f"Config missing required sections: {missing}")

    bbox = raw["aoi"].get("bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4 and bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        raise ValueError(f"aoi.bbox must be [min_lon, min_lat, max_lon, max_lat], got {bbox}")

    weights = raw["risk"]["weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"risk.weights must sum to 1.0, got {total:.3f}")
