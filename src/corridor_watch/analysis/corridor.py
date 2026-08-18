"""Corridor geometry: segment transmission lines into analysis spans and buffer them.

Grid operators manage vegetation per span (pylon to pylon). We approximate
spans by cutting each line into fixed-length segments in a projected CRS,
then buffering each segment to the regulatory clearance corridor width.
"""
from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import substring


def segment_lines(
    lines: gpd.GeoDataFrame,
    segment_length_m: float,
    crs_utm: str,
) -> gpd.GeoDataFrame:
    """Cut every line into consecutive segments of ``segment_length_m``.

    Returns a GeoDataFrame in ``crs_utm`` with columns:
    ``line_id``, ``segment_id``, ``km_start``, ``km_end``, ``geometry``.
    The trailing remainder of each line is kept as its own (shorter) segment
    so no length is silently dropped.
    """
    if lines.empty:
        raise ValueError("No transmission lines supplied — cannot build corridor segments.")
    if segment_length_m <= 0:
        raise ValueError(f"segment_length_m must be positive, got {segment_length_m}")

    proj = lines.to_crs(crs_utm)
    records: list[dict] = []
    for line_id, geom in zip(proj.index, proj.geometry):
        if geom is None or geom.is_empty:
            continue
        parts = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
        offset = 0.0
        for part in parts:
            length = part.length
            start = 0.0
            while start < length - 1e-6:
                end = min(start + segment_length_m, length)
                seg = substring(part, start, end)
                if isinstance(seg, LineString) and seg.length > 1e-6:
                    records.append(
                        {
                            "line_id": line_id,
                            "segment_id": f"{line_id}_{len(records):04d}",
                            "km_start": round((offset + start) / 1000.0, 3),
                            "km_end": round((offset + end) / 1000.0, 3),
                            "geometry": seg,
                        }
                    )
                start = end
            offset += length

    if not records:
        raise ValueError("Line segmentation produced no segments — check input geometries.")
    return gpd.GeoDataFrame(records, crs=crs_utm)


def buffer_segments(segments: gpd.GeoDataFrame, buffer_m: float) -> gpd.GeoDataFrame:
    """Buffer each span to the clearance corridor polygon (flat caps).

    Flat caps avoid double-counting pixels at span boundaries between
    consecutive segments of the same line.
    """
    if buffer_m <= 0:
        raise ValueError(f"buffer_m must be positive, got {buffer_m}")
    out = segments.copy()
    out["geometry"] = out.geometry.buffer(buffer_m, cap_style="flat")
    out["corridor_area_m2"] = out.geometry.area.round(1)
    return out
