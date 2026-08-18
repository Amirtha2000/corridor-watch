"""Offline demo dataset generator.

Produces a physically plausible, seeded Sentinel-2-like scene pair (10 m
red + NIR reflectance) and a transmission-line geometry for the configured
AOI, so the entire pipeline runs end-to-end without network access.

This is honest synthetic data for demonstrating the *pipeline*: spatially
correlated reflectance fields, a forest/field landscape, a cleared corridor
under the line, and injected vegetation regrowth patches encroaching into
the corridor between the two epochs. Swap in real imagery with
``corridor-watch fetch`` when online.
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import gaussian_filter
from shapely.geometry import LineString

from corridor_watch.config import Config

log = logging.getLogger(__name__)

RES_M = 10.0
SEED = 20260818


def _correlated_field(shape: tuple[int, int], rng: np.random.Generator, sigma: float) -> np.ndarray:
    """Smooth random field in [0, 1] — the texture of a real landscape."""
    field = gaussian_filter(rng.standard_normal(shape), sigma=sigma)
    field -= field.min()
    return field / (field.max() + 1e-12)


def generate(cfg: Config, out_dir: str | Path) -> dict:
    """Write demo rasters + line vector; return paths dict matching the fetch API."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    # --- grid over the AOI in UTM --------------------------------------------
    import pyproj

    tf = pyproj.Transformer.from_crs("EPSG:4326", cfg.crs_utm, always_xy=True)
    min_x, min_y = tf.transform(cfg.bbox[0], cfg.bbox[1])
    max_x, max_y = tf.transform(cfg.bbox[2], cfg.bbox[3])
    width = int((max_x - min_x) // RES_M)
    height = int((max_y - min_y) // RES_M)
    transform = from_origin(min_x, max_y, RES_M, RES_M)
    shape = (height, width)
    log.info("demo grid: %dx%d px @ %.0f m (UTM)", width, height, RES_M)

    # --- transmission line: gentle diagonal across the AOI -------------------
    n_pts = 8
    xs = np.linspace(min_x + 0.05 * (max_x - min_x), max_x - 0.05 * (max_x - min_x), n_pts)
    ys = np.linspace(min_y + 0.25 * (max_y - min_y), max_y - 0.30 * (max_y - min_y), n_pts)
    ys += 400.0 * np.sin(np.linspace(0, 2.2, n_pts))  # slight routing bends
    line_utm = LineString(zip(xs, ys))
    lines = gpd.GeoDataFrame(
        {"osm_id": [990001], "voltage_kv": [380.0], "name": ["Demo 380 kV corridor"]},
        geometry=[line_utm],
        crs=cfg.crs_utm,
    ).to_crs("EPSG:4326")
    lines_path = out_dir / "power_lines.geojson"
    lines.to_file(lines_path, driver="GeoJSON")

    # --- landscape: NDVI-like base field -------------------------------------
    base = _correlated_field(shape, rng, sigma=18)          # broad land-cover pattern
    texture = _correlated_field(shape, rng, sigma=3)        # within-patch texture
    forest_mask = base > 0.55
    ndvi_base = np.where(forest_mask, 0.62 + 0.18 * texture, 0.18 + 0.30 * texture)

    # cleared maintenance corridor under the line (managed vegetation, low NDVI)
    corridor_mask = rasterize(
        [(line_utm.buffer(cfg.buffer_m), 1)], out_shape=shape, transform=transform, fill=0
    ).astype(bool)
    ndvi_base = np.where(corridor_mask, 0.22 + 0.12 * texture, ndvi_base)

    # --- epoch 2: seasonal drift + regrowth patches encroaching the corridor --
    ndvi_monitor = ndvi_base + rng.normal(0.0, 0.015, shape)
    # two "hotspot" stretches with clustered regrowth (a realistic pattern:
    # spans skipped in the last maintenance cycle), plus scattered patches
    hotspots = [0.28, 0.62]
    positions = list(np.sort(rng.uniform(0.05, 0.95, 10)))
    for h in hotspots:
        positions += list(np.clip(h + rng.normal(0, 0.015, 6), 0.02, 0.98))
    for t in positions:
        px, py = line_utm.interpolate(t, normalized=True).coords[0]
        jitter = rng.normal(0, cfg.buffer_m * 0.6, 2)
        cx = int((px + jitter[0] - min_x) / RES_M)
        cy = int((max_y - (py + jitter[1])) / RES_M)
        r = int(rng.uniform(2, 8))  # 20–80 m regrowth patches
        yy, xx = np.ogrid[:height, :width]
        patch = (yy - cy) ** 2 + (xx - cx) ** 2 <= r**2
        ndvi_monitor = np.where(patch, np.clip(ndvi_monitor + rng.uniform(0.18, 0.35), 0, 0.92), ndvi_monitor)

    # --- back out red/NIR reflectance consistent with the target NDVI ---------
    def to_bands(ndvi_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        nir = 0.28 + 0.14 * _correlated_field(shape, rng, sigma=6)
        ndvi_arr = np.clip(ndvi_arr, -0.95, 0.95)
        red = nir * (1 - ndvi_arr) / (1 + ndvi_arr)
        return red.astype("float32"), nir.astype("float32")

    paths: dict = {"lines": lines_path}
    for label, ndvi_arr in [("baseline", ndvi_base), ("monitor", ndvi_monitor)]:
        red, nir = to_bands(ndvi_arr)
        for band_name, data in [("red", red), ("nir", nir)]:
            profile = {
                "driver": "GTiff", "height": height, "width": width, "count": 1,
                "dtype": "float32", "crs": cfg.crs_utm, "transform": transform,
                "compress": "deflate",
            }
            p = out_dir / f"{label}_{band_name}.tif"
            with rasterio.open(p, "w", **profile) as dst:
                dst.write(data, 1)
            paths[f"{label}_{band_name}"] = p
    log.info("demo scene pair written to %s", out_dir)
    return paths
