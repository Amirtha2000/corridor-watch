"""Per-segment vegetation risk scoring.

For every corridor segment we extract zonal statistics from the NDVI and
dNDVI rasters and combine three interpretable drivers into a 0–1 score:

- ``veg_fraction``   — how much of the corridor is densely vegetated *now*
- ``ndvi_p90``       — how vigorous the densest canopy is (proximity proxy)
- ``growth_fraction``— how much of the corridor significantly greened up
                       since the baseline epoch (encroachment dynamics)

The score is a transparent weighted sum, not a black box: every driver is
kept as a column so an analyst can explain *why* a span ranks high — which
is exactly the conversation you have with a grid operator's field team.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask


def zonal_stats(
    segments: gpd.GeoDataFrame,
    ndvi_path: str,
    dndvi_path: str,
    veg_threshold: float,
    growth_threshold: float,
) -> gpd.GeoDataFrame:
    """Attach zonal vegetation statistics to each corridor polygon."""
    out = segments.copy()
    stats: list[dict] = []

    with rasterio.open(ndvi_path) as nd, rasterio.open(dndvi_path) as dd:
        if nd.crs != dd.crs or nd.transform != dd.transform or nd.shape != dd.shape:
            raise ValueError("NDVI and dNDVI rasters are not on the same grid.")
        if str(nd.crs) != str(segments.crs):
            raise ValueError(
                f"Segments CRS ({segments.crs}) != raster CRS ({nd.crs}). Reproject first."
            )
        ndvi = nd.read(1)
        dndvi = dd.read(1)
        transform = nd.transform

        for geom in out.geometry:
            mask = geometry_mask(
                [geom], out_shape=ndvi.shape, transform=transform, invert=True
            )
            nd_vals = ndvi[mask]
            dd_vals = dndvi[mask]
            nd_valid = nd_vals[np.isfinite(nd_vals)]
            dd_valid = dd_vals[np.isfinite(dd_vals)]

            if nd_valid.size == 0:
                stats.append(
                    {
                        "n_pixels": 0,
                        "valid_fraction": 0.0,
                        "ndvi_mean": np.nan,
                        "ndvi_p90": np.nan,
                        "veg_fraction": np.nan,
                        "growth_fraction": np.nan,
                    }
                )
                continue

            stats.append(
                {
                    "n_pixels": int(nd_vals.size),
                    "valid_fraction": round(nd_valid.size / nd_vals.size, 3),
                    "ndvi_mean": round(float(nd_valid.mean()), 4),
                    "ndvi_p90": round(float(np.percentile(nd_valid, 90)), 4),
                    "veg_fraction": round(float((nd_valid > veg_threshold).mean()), 4),
                    "growth_fraction": round(
                        float((dd_valid > growth_threshold).mean()) if dd_valid.size else 0.0, 4
                    ),
                }
            )

    for key in stats[0]:
        out[key] = [s[key] for s in stats]
    return out


def score(
    segments: gpd.GeoDataFrame,
    weights: dict[str, float],
    thresholds: dict[str, float],
) -> gpd.GeoDataFrame:
    """Combine drivers into ``risk_score`` (0–1) and ``risk_class``.

    ``ndvi_p90`` is rescaled from [0, 1] NDVI to a 0–1 driver via clipping at
    the plausible canopy range [0.2, 0.9] so bare corridors score ~0.
    Segments with no valid pixels get ``risk_class = "no-data"`` — surfacing
    them is a delivery-quality feature, not an error to hide.
    """
    required = {"veg_fraction", "ndvi_p90", "growth_fraction"}
    missing = required - set(segments.columns)
    if missing:
        raise ValueError(f"Segments missing driver columns: {sorted(missing)}")
    if set(weights) != required:
        raise ValueError(f"weights must have exactly keys {sorted(required)}, got {sorted(weights)}")

    out = segments.copy()
    p90_driver = ((out["ndvi_p90"].clip(0.2, 0.9) - 0.2) / 0.7).fillna(0.0)
    out["risk_score"] = (
        weights["veg_fraction"] * out["veg_fraction"].fillna(0.0)
        + weights["ndvi_p90"] * p90_driver
        + weights["growth_fraction"] * out["growth_fraction"].fillna(0.0)
    ).round(4)

    def classify(row) -> str:
        if row["n_pixels"] == 0 or row["valid_fraction"] == 0.0:
            return "no-data"
        if row["risk_score"] >= thresholds["high"]:
            return "high"
        if row["risk_score"] >= thresholds["medium"]:
            return "medium"
        return "low"

    out["risk_class"] = out.apply(classify, axis=1)
    out["rank"] = (
        out["risk_score"].rank(ascending=False, method="first").astype(int)
    )
    return out.sort_values("rank")
