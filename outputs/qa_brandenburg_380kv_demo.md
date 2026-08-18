# QA report — brandenburg_380kv_demo

Generated: 2026-08-18 11:21 UTC  
**Verdict: PASS**  
Checks: 25 total · 0 blocking failure(s) · 0 warning(s)

| Status | Severity | Check | Result |
|--------|----------|-------|--------|
| ✅ | ⛔ error | input power lines: at least 1 feature(s) | 1 feature(s) present |
| ✅ | ⛔ error | input power lines: CRS matches expected | vector CRS EPSG:4326 vs expected EPSG:4326 |
| ✅ | ⛔ error | input power lines: geometries valid and non-empty | 0 invalid, 0 empty geometries |
| ✅ | ⛔ error | NDVI baseline: CRS matches AOI grid | raster CRS EPSG:32633 vs expected EPSG:32633 |
| ✅ | ⛔ error | NDVI baseline: nodata fraction <= 10% | nodata fraction = 0.00% |
| ✅ | ⛔ error | NDVI baseline: values within (-1.0, 1.0) | observed range [0.181, 0.794] |
| ✅ | ⚠️ warning | NDVI baseline: non-degenerate variance | std = 0.19292 (a constant raster usually means a broken upstream read) |
| ✅ | ℹ️ info | NDVI baseline: grid summary | 829x655 px @ 10.0 m |
| ✅ | ⛔ error | NDVI monitor: CRS matches AOI grid | raster CRS EPSG:32633 vs expected EPSG:32633 |
| ✅ | ⛔ error | NDVI monitor: nodata fraction <= 10% | nodata fraction = 0.00% |
| ✅ | ⛔ error | NDVI monitor: values within (-1.0, 1.0) | observed range [0.166, 0.920] |
| ✅ | ⚠️ warning | NDVI monitor: non-degenerate variance | std = 0.19356 (a constant raster usually means a broken upstream read) |
| ✅ | ℹ️ info | NDVI monitor: grid summary | 829x655 px @ 10.0 m |
| ✅ | ⛔ error | dNDVI: CRS matches AOI grid | raster CRS EPSG:32633 vs expected EPSG:32633 |
| ✅ | ⛔ error | dNDVI: nodata fraction <= 10% | nodata fraction = 0.00% |
| ✅ | ⛔ error | dNDVI: values within (-2.0, 2.0) | observed range [-0.070, 0.652] |
| ✅ | ⚠️ warning | dNDVI: non-degenerate variance | std = 0.02279 (a constant raster usually means a broken upstream read) |
| ✅ | ℹ️ info | dNDVI: grid summary | 829x655 px @ 10.0 m |
| ✅ | ⛔ error | corridor segments: at least 5 feature(s) | 33 feature(s) present |
| ✅ | ⛔ error | corridor segments: CRS matches expected | vector CRS EPSG:32633 vs expected EPSG:32633 |
| ✅ | ⛔ error | corridor segments: geometries valid and non-empty | 0 invalid, 0 empty geometries |
| ✅ | ⛔ error | delivery: >= 5 scored segments | 33 segments scored |
| ✅ | ⛔ error | delivery: risk scores within [0, 1] | score range [0.033, 0.818] |
| ✅ | ⚠️ warning | delivery: no-data segments <= 20% | 0 segment(s) (0%) had no valid pixels |
| ✅ | ℹ️ info | delivery: risk class distribution | high=4, low=28, medium=1 |

## Run context

- **config**: corridor_brandenburg.yaml
- **aoi**: brandenburg_380kv_demo
- **segments**: 33
- **high_risk**: 4