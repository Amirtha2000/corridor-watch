import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, Polygon

from corridor_watch import qa
from corridor_watch.qa.checks import QAGateError, Severity

UTM = "EPSG:32633"


def write_raster(tmp_path, arr, crs=UTM, name="test.tif"):
    path = tmp_path / name
    profile = {
        "driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1], "count": 1,
        "dtype": "float32", "crs": crs, "transform": from_origin(400000, 5780000, 10, 10),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)
    return str(path)


def test_clean_raster_passes(tmp_path):
    arr = np.random.default_rng(0).uniform(-0.2, 0.9, (20, 20))
    results = qa.run_raster_checks(write_raster(tmp_path, arr), "ndvi", UTM, (-1, 1), 0.1)
    assert all(r.passed for r in results)


def test_wrong_crs_is_blocking(tmp_path):
    arr = np.random.default_rng(0).uniform(0, 0.5, (10, 10))
    results = qa.run_raster_checks(write_raster(tmp_path, arr, crs="EPSG:32632"), "ndvi", UTM, (-1, 1), 0.1)
    failed = [r for r in results if not r.passed]
    assert failed and failed[0].severity == Severity.ERROR
    with pytest.raises(QAGateError):
        qa.gate(results)


def test_excessive_nodata_is_blocking(tmp_path):
    arr = np.full((10, 10), np.nan)
    arr[0, 0] = 0.5
    results = qa.run_raster_checks(write_raster(tmp_path, arr), "ndvi", UTM, (-1, 1), 0.1)
    assert any(not r.passed and "nodata" in r.check for r in results)


def test_out_of_range_values_blocked(tmp_path):
    arr = np.full((10, 10), 3.7)  # impossible NDVI → symptom of unscaled DNs upstream
    results = qa.run_raster_checks(write_raster(tmp_path, arr), "ndvi", UTM, (-1, 1), 0.1)
    assert any(not r.passed and "within" in r.check for r in results)


def test_constant_raster_warns_but_does_not_block(tmp_path):
    arr = np.full((10, 10), 0.42)
    results = qa.run_raster_checks(write_raster(tmp_path, arr), "ndvi", UTM, (-1, 1), 0.1)
    degenerate = [r for r in results if "degenerate" in r.check]
    assert degenerate and not degenerate[0].passed
    qa.gate(results)  # warnings alone must not raise


def test_vector_checks_catch_invalid_geometry():
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])  # self-intersecting
    gdf = gpd.GeoDataFrame(geometry=[bowtie], crs=UTM)
    results = qa.run_vector_checks(gdf, "segments", expected_crs=UTM)
    assert any(not r.passed and "valid" in r.check for r in results)


def test_vector_checks_min_features():
    gdf = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])], crs=UTM)
    results = qa.run_vector_checks(gdf, "lines", min_features=5)
    assert any(not r.passed for r in results)


def test_report_written(tmp_path):
    gdf = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])], crs=UTM)
    results = qa.run_vector_checks(gdf, "lines", expected_crs=UTM)
    md, js = qa.write_report(results, tmp_path, "unit_test", {"aoi": "test"})
    assert md.exists() and js.exists()
    assert "Verdict" in md.read_text()
