# Implementation plan

Order of work, chosen so that every step leaves the repo in a runnable, tested
state. Analysis core first (pure functions, easy to test), IO at the edges,
orchestration last.

## Milestones

| # | Step | Definition of done |
|---|------|--------------------|
| 1 | Project scaffold | installable package, pyproject, license, gitignore |
| 2 | Config layer | YAML per corridor, fail-fast validation, typed accessors |
| 3 | Spectral indices | ndvi/delta with NaN semantics, unit tests green |
| 4 | Corridor geometry | segmentation + buffering, length-conservation test |
| 5 | QA framework | structured checks, severity gate, md+json report, tests |
| 6 | Risk scoring | zonal stats + transparent score, no-data handling, tests |
| 7 | Data fetch | STAC windowed COG reads + Overpass lines (online mode) |
| 8 | Demo generator | seeded offline scene pair so the pipeline runs anywhere |
| 9 | CLI pipeline | demo / fetch / run wired end-to-end, QA-gated delivery |
| 10 | Delivery map | interactive Leaflet map with per-span driver popups |
| 11 | Orchestration | Prefect flow, retries on network stages only, optional dep |
| 12 | CI | lint + tests + end-to-end demo run on every push |
| 13 | Docs & example outputs | README with design decisions, example delivery committed |

## Testing strategy

- Unit tests per analysis module, written against the pseudocode contracts,
  with the failure modes as first-class cases (zero denominator, remainder
  segment, no-data span, wrong CRS, constant raster, invalid geometry).
- The QA layer itself gets tests: a QA system nobody tests is decoration.
- CI runs the full demo pipeline, not just unit tests, so a broken wiring
  between stages cannot slip through.

## Tooling

Standard stack: Python, GeoPandas/Rasterio/Shapely, QGIS for visual checks of
intermediate rasters and geometries. I use AI coding assistants (Claude) for
boilerplate drafting and as a rubber duck, with a hard rule: every contract,
threshold and QA gate is my decision, written down before generation, and
nothing is kept that I haven't read and covered with a test. The failure-mode
tests (zero-denominator NDVI, dropped remainder segments, no-data spans scored
low) exist precisely because generated first drafts tend to miss them.

## Risks / watch-outs

- Geometry ops must happen in a projected CRS (UTM 33N for this AOI); buffers
  in degrees are a classic silent bug. Config carries the CRS explicitly.
- SCL is 20 m vs 10 m bands: resample on read, keep the 10 m grid as reference.
- Overpass and STAC are flaky under load: retries belong in orchestration for
  exactly these stages and nowhere else.
- Keep raw data out of git (data/ ignored); example outputs are small and go
  in outputs/ deliberately in the final step.

## Out of scope for v0.1 (documented as limitations)

- Per-pixel cloud masking of analysis rasters (scene-level filter + SCL at
  fetch time only).
- Median-composite baselines.
- Height-aware clearance risk (needs LiDAR/stereo/InSAR); NDVI change is the
  where-to-look layer.
