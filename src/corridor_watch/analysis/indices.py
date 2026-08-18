"""Spectral index computation on Sentinel-2 reflectance arrays."""
from __future__ import annotations

import numpy as np


def ndvi(red: np.ndarray, nir: np.ndarray, nodata: float | None = None) -> np.ndarray:
    """Compute NDVI = (NIR - RED) / (NIR + RED).

    Inputs are surface reflectance (any consistent scaling). Pixels where the
    denominator is ~0, either band is non-finite, or either band equals
    ``nodata`` are returned as NaN rather than silently clipped — downstream
    QA counts NaN fractions explicitly.
    """
    red = red.astype("float64")
    nir = nir.astype("float64")

    invalid = ~np.isfinite(red) | ~np.isfinite(nir)
    if nodata is not None:
        invalid |= (red == nodata) | (nir == nodata)

    denom = nir + red
    invalid |= np.abs(denom) < 1e-9

    with np.errstate(divide="ignore", invalid="ignore"):
        out = (nir - red) / denom
    out[invalid] = np.nan
    return out


def delta(baseline: np.ndarray, monitor: np.ndarray) -> np.ndarray:
    """Change layer (monitor - baseline). NaN where either input is NaN."""
    if baseline.shape != monitor.shape:
        raise ValueError(
            f"Shape mismatch between epochs: baseline {baseline.shape} vs monitor {monitor.shape}. "
            "Epochs must be co-registered on the same grid before differencing."
        )
    return monitor - baseline
