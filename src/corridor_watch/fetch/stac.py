"""Fetch Sentinel-2 L2A red/NIR/SCL subsets from the AWS open-data archive.

Uses the Element 84 Earth Search STAC API and windowed reads against the
Cloud-Optimized GeoTIFFs, so only the AOI subset is downloaded — never a
whole 100x100 km granule. Requires internet access; in offline environments
use ``corridor_watch.demo`` instead.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

log = logging.getLogger(__name__)


def search_scenes(
    stac_api: str,
    collection: str,
    bbox: list[float],
    date_range: tuple[str, str],
    max_cloud_cover: float,
) -> list:
    """Return matching STAC items sorted by cloud cover (clearest first)."""
    from pystac_client import Client  # optional dependency: pip install .[fetch]

    client = Client.open(stac_api)
    search = client.search(
        collections=[collection],
        bbox=bbox,
        datetime=f"{date_range[0]}/{date_range[1]}",
        query={"eo:cloud_cover": {"lt": max_cloud_cover}},
    )
    items = list(search.items())
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100.0))
    log.info("STAC search: %d scene(s) < %.0f%% cloud in %s", len(items), max_cloud_cover, date_range)
    if not items:
        raise RuntimeError(
            f"No {collection} scenes found for bbox={bbox}, dates={date_range}, "
            f"cloud<{max_cloud_cover}%. Widen the date range or relax the cloud filter."
        )
    return items


def download_subset(
    item,
    bands: dict[str, str],
    bbox_wgs84: list[float],
    crs_utm: str,
    out_dir: str | Path,
    label: str,
) -> dict[str, Path]:
    """Windowed-read each requested band asset over the AOI; write local GeoTIFFs.

    Returns {logical_band_name: path}. SCL (20 m) is resampled by rasterio on
    read to match the 10 m grid via ``out_shape``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    ref_shape = None
    ref_transform = None
    for logical, asset_key in bands.items():
        href = item.assets[asset_key].href
        with rasterio.open(href) as src:
            bounds_native = transform_bounds("EPSG:4326", src.crs, *bbox_wgs84)
            window = from_bounds(*bounds_native, transform=src.transform)
            if logical == "scl" and ref_shape is not None:
                data = src.read(1, window=window, out_shape=ref_shape, resampling=rasterio.enums.Resampling.nearest)
                transform = ref_transform
            else:
                data = src.read(1, window=window)
                transform = src.window_transform(window)
                ref_shape, ref_transform = data.shape, transform

            profile = {
                "driver": "GTiff",
                "height": data.shape[0],
                "width": data.shape[1],
                "count": 1,
                "dtype": data.dtype,
                "crs": src.crs,
                "transform": transform,
                "compress": "deflate",
            }
            path = out_dir / f"{label}_{logical}.tif"
            with rasterio.open(path, "w", **profile) as dst:
                dst.write(data, 1)
            paths[logical] = path
            log.info("wrote %s (%s px)", path.name, "x".join(map(str, data.shape)))
    return paths


def cloud_fraction_from_scl(scl: np.ndarray) -> float:
    """Fraction of AOI pixels flagged cloud/shadow in the Scene Classification Layer.

    SCL classes: 3=cloud shadow, 8=cloud medium prob, 9=cloud high prob, 10=thin cirrus.
    """
    flagged = np.isin(scl, [3, 8, 9, 10])
    return float(flagged.mean()) if scl.size else 1.0
