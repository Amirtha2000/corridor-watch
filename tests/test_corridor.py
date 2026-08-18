import geopandas as gpd
import pytest
from shapely.geometry import LineString

from corridor_watch.analysis import corridor

UTM = "EPSG:32633"


def straight_line_gdf(length_m=1000.0):
    return gpd.GeoDataFrame(
        {"osm_id": [1]}, geometry=[LineString([(400000, 5780000), (400000 + length_m, 5780000)])], crs=UTM
    )


def test_segment_count_and_remainder():
    segs = corridor.segment_lines(straight_line_gdf(1050.0), 250.0, UTM)
    # 4 full segments + one 50 m remainder — nothing silently dropped
    assert len(segs) == 5
    assert segs.geometry.length.sum() == pytest.approx(1050.0, abs=0.1)


def test_segment_km_markers_are_monotonic():
    segs = corridor.segment_lines(straight_line_gdf(1000.0), 250.0, UTM)
    assert list(segs["km_start"]) == [0.0, 0.25, 0.5, 0.75]
    assert list(segs["km_end"]) == [0.25, 0.5, 0.75, 1.0]


def test_empty_input_raises():
    empty = gpd.GeoDataFrame(geometry=[], crs=UTM)
    with pytest.raises(ValueError, match="No transmission lines"):
        corridor.segment_lines(empty, 250.0, UTM)


def test_invalid_segment_length_raises():
    with pytest.raises(ValueError, match="positive"):
        corridor.segment_lines(straight_line_gdf(), -5.0, UTM)


def test_buffer_produces_expected_area():
    segs = corridor.segment_lines(straight_line_gdf(500.0), 250.0, UTM)
    buf = corridor.buffer_segments(segs, 35.0)
    # flat caps: area = length * 2*buffer
    assert buf["corridor_area_m2"].iloc[0] == pytest.approx(250.0 * 70.0, rel=0.01)
