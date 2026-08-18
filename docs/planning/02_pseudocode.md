# Pseudocode — module contracts before code

Writing the contracts down first so the tests have something to assert against
and so failure semantics are decided up front, not discovered in review. This
also gives me a fixed reference to validate AI-drafted boilerplate against —
if generated code disagrees with the contract, the contract wins.

## indices

```
ndvi(red, nir, nodata=None) -> float array
    invalid := not finite(red) or not finite(nir)
               or band == nodata (if given)
               or |nir + red| ~ 0          # water/shadow: DO NOT return inf
    out := (nir - red) / (nir + red)
    out[invalid] := NaN                    # QA counts NaN fraction later
    return out

delta(baseline, monitor)
    require same shape                     # else raise: epochs not co-registered
    return monitor - baseline              # NaN propagates
```

## corridor

```
segment_lines(lines, seg_len, crs_utm) -> spans
    require lines non-empty, seg_len > 0
    project to UTM
    for each line part:
        walk 0..length in steps of seg_len
        emit substring segment with km_start / km_end markers
        remainder shorter than seg_len -> ITS OWN segment  # conserve length
    require at least one segment produced

buffer_segments(spans, buffer_m) -> corridor polygons
    buffer with FLAT caps                  # no double counting at span joints
    record corridor_area_m2
```

## risk

```
zonal_stats(spans, ndvi_raster, dndvi_raster, veg_thr, growth_thr)
    require both rasters on same grid and same CRS as spans
    for each polygon:
        mask pixels; keep finite ones
        n_pixels, valid_fraction
        ndvi_mean, ndvi_p90
        veg_fraction    := share(ndvi > veg_thr)
        growth_fraction := share(dndvi > growth_thr)
    zero valid pixels -> stats are NaN, valid_fraction 0   # flagged, not faked

score(spans, weights, thresholds)
    require driver columns present; require weights keys exact
    p90_driver := rescale clip(ndvi_p90, 0.2, 0.9) to 0..1
    risk_score := w1*veg_fraction + w2*p90_driver + w3*growth_fraction
    class      := high / medium / low by thresholds
                  "no-data" when no valid pixels            # never "low"!
    rank descending by score
```

## qa

```
CheckResult { check, passed, severity(info|warning|error), message, details }

raster checks(path):  CRS == expected; nodata fraction <= max;
                      values in valid range; std > 0 (constant raster
                      usually means broken upstream read) -> warning
vector checks(gdf):   count >= min; CRS == expected; geometries valid+non-empty
output checks(scored): count >= min; scores within [0,1];
                       no-data spans <= 20% -> warning; class distribution -> info

gate(results, fail_on=("error",)):
    any failed check with blocking severity -> raise QAGateError
    # deliver nothing rather than deliver wrong

report(results) -> markdown (for humans) + json (for dashboards/regression)
```

## pipeline (cli run)

```
load config (fail fast on malformed yaml: bbox sane, weights sum to 1)
read lines            -> vector checks
ndvi both epochs      -> write rasters
dndvi                 -> write raster
raster checks all three
segment + buffer      -> vector checks
zonal stats + score   -> output checks
write QA report ALWAYS (even on failure)
gate                  -> abort here if blocking failures (unless --override-qa)
write geojson + csv + interactive map
```

## fetch (online mode)

```
stac: search collection sentinel-2-l2a, bbox, date range, cloud < max
      sort by cloud cover, take clearest
      windowed read red/nir/scl from COGs over AOI only
osm:  overpass query power=line in bbox
      parse voltage tags ("220000;110000", "110 kV" ...) -> take max, kV
      unparseable voltage -> KEEP and flag, don't silently drop
```

## demo (offline mode)

```
seeded rng
smooth correlated random fields -> forest/field NDVI landscape
cleared low-NDVI strip under the line (managed corridor)
epoch2 := epoch1 + noise + regrowth patches clustered near line
          (2 hotspot stretches = spans missed in last maintenance cycle)
back out red/nir from target NDVI so pipeline sees real band math
```
