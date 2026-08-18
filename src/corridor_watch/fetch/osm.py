"""Fetch power transmission line geometries from OpenStreetMap (Overpass API)."""
from __future__ import annotations

import logging

import geopandas as gpd
import requests
from shapely.geometry import LineString

log = logging.getLogger(__name__)


def fetch_power_lines(
    overpass_api: str,
    bbox: list[float],
    min_voltage_kv: float = 110.0,
    timeout_s: int = 90,
) -> gpd.GeoDataFrame:
    """Query OSM ``power=line`` ways inside the AOI bbox.

    Returns a WGS84 GeoDataFrame with ``osm_id``, ``voltage_kv``, ``name``.
    Ways without a parseable voltage tag are kept (voltage_kv = NaN) but
    flagged, so the QA layer — not a silent filter — decides what to do.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    query = f"""
    [out:json][timeout:{timeout_s}];
    way["power"="line"]({min_lat},{min_lon},{max_lat},{max_lon});
    out geom;
    """
    resp = requests.post(overpass_api, data={"data": query}, timeout=timeout_s + 30)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])

    records = []
    for el in elements:
        coords = [(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])]
        if len(coords) < 2:
            continue
        tags = el.get("tags", {})
        records.append(
            {
                "osm_id": el["id"],
                "voltage_kv": _parse_voltage_kv(tags.get("voltage")),
                "name": tags.get("name", ""),
                "geometry": LineString(coords),
            }
        )

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326") if records else gpd.GeoDataFrame(
        columns=["osm_id", "voltage_kv", "name", "geometry"], crs="EPSG:4326"
    )
    if len(gdf):
        keep = gdf["voltage_kv"].isna() | (gdf["voltage_kv"] >= min_voltage_kv)
        dropped = int((~keep).sum())
        if dropped:
            log.info("dropped %d line(s) below %.0f kV", dropped, min_voltage_kv)
        gdf = gdf[keep].reset_index(drop=True)
    log.info("fetched %d transmission line(s) from OSM", len(gdf))
    return gdf


def _parse_voltage_kv(raw: str | None) -> float | None:
    """OSM voltage tags are messy: '380000', '220000;110000', '110 kV'…

    Take the highest value found; return kV; None when unparseable.
    """
    if not raw:
        return None
    volts = []
    for token in str(raw).replace("kV", "000").split(";"):
        digits = "".join(c for c in token if c.isdigit())
        if digits:
            volts.append(int(digits))
    return max(volts) / 1000.0 if volts else None
