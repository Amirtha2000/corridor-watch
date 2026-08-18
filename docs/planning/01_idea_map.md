# Idea map — what to build, and why this of all things

## Motivation: why this project

I want a project that proves I can run the *delivery side* of satellite
analytics, not just fit a model in a notebook. That constraint kills most of
the usual portfolio ideas straight away:

- **Land-cover classification on a benchmark dataset** — rejected. Thousands
  exist, there is no customer in the story, and accuracy on EuroSAT says
  nothing about whether I can ship a correct product to someone who depends
  on it.
- **Deforestation / burned-area mapper** — rejected. Scientifically
  interesting, but the output is a map someone looks at once. No recurring
  delivery, so no room to show pipeline thinking, QA, or operations.
- **Flood extent mapping with Sentinel-1** — close second. Kept aside because
  the SAR preprocessing rabbit hole would eat the time I want to spend on the
  part that actually differentiates: delivery quality.
- **Vegetation encroachment on transmission corridors — chosen.** It has a
  paying-customer shape: grid operators are legally required to keep clearance
  corridors free, outages and wildfire ignitions are expensive and
  career-ending, and helicopter/foot patrols over thousands of km are the
  costly status quo being replaced by satellite screening. The problem is
  *recurring* (vegetation regrows; imagery arrives every ~5 days), which is
  exactly what makes pipelines, orchestration and QA gates real requirements
  instead of decoration. And it is honest about scale: 10 m free imagery is
  genuinely useful here as a where-to-look screening layer.

The deeper reason: in a monitoring product, the thing being sold is not a map,
it is *trust in a stream of deliveries*. So the design center of this project
is not the NDVI math (that part is easy) — it is everything wrapped around it
that decides whether a wrong number can reach a customer.

## Mind map

```mermaid
mindmap
  root((Corridor vegetation monitoring))
    Problem
      Vegetation into clearance corridor -> outages, wildfire ignition
      Operators must inspect 1000s of km; patrols are slow and expensive
      Satellite = continuous screening that tells crews WHERE to go
    Data
      Sentinel-2 L2A
        free, 10 m, ~5-day revisit -> recurring product is feasible at zero data cost
        AWS open-data COGs -> windowed HTTP reads, never a full 800 MB granule for 5 km of line
        Earth Search STAC for discovery, cloud-cover filter at query time
      OSM power=line via Overpass
        free, global, good enough geometry for corridor screening
        voltage tags are messy ("220000;110000", "110 kV") -> parsing is a real-data test
      rejected alternatives
        Landsat: 30 m pixel vs 35 m corridor half-width -> 1-2 pixels across, too coarse
        Planet/commercial: better res, but cost kills the reproducibility of a portfolio piece
    Method
      NDVI now + NDVI change vs same-season baseline
        why NDVI: robust, universally understood, defensible in front of a customer
        why change: absolute greenness flags every healthy forest; GROWTH is the risk signal
        why same-season: Jul/Aug vs Jul/Aug cancels phenology, else spring greening = false alarms
        openly a proxy: NDVI is not canopy height -> screening layer, not clearance measurement
      corridor = line buffered 35 m, cut into 250 m spans
        spans ~ pylon-to-pylon: crews plan work per span, so the product must speak in spans
        flat buffer caps so adjacent spans never double-count pixels
      transparent weighted score, three drivers
        why not ML: no labels, and a black box is unsellable when a planner asks "why is this red?"
        every driver stays a column -> the popup IS the explanation
    Quality  [the differentiator]
      a wrong delivery that LOOKS right is the expensive failure, not a crash
      QA gates as a pipeline stage with severity contract
        error blocks the delivery, warning flags it, info traces it
        checks target root-cause symptoms: constant raster = broken upstream read,
        NDVI > 1 = unscaled DNs, CRS mismatch = wrong-grid delivery
      QA report every run: markdown for a PM, JSON for regression tracking
    Outputs
      risk-ranked GeoJSON + CSV (QGIS/PostGIS-ready)
      interactive Leaflet map, driver popups per span
    Ops
      one YAML per corridor -> same code retargets a rail line by changing a bbox and a tag filter
      Prefect flow: retries ONLY on network stages; deterministic failures need a human, not a retry
      seeded offline demo mode -> anyone can run it, CI can prove the wiring end to end
```

## Decisions locked in at this stage, with reasons

1. **Sentinel-2 over Landsat/commercial.** 10 m resolves a 70 m-wide corridor
   into ~7 pixels across — enough for fraction-based statistics. Landsat's
   30 m does not. Commercial imagery would break the "anyone can reproduce
   this" property that a portfolio project lives on.
2. **Change detection against a same-season baseline.** A single-date
   vegetation map cannot separate "healthy forest that was always there,
   outside the wire zone" from "regrowth advancing into the corridor since
   last maintenance". The delta is the signal; the season-matching is what
   keeps the delta honest.
3. **Weighted sum of three interpretable drivers, not a classifier.** I have
   no ground-truth labels, and inventing them would be worse than honest
   heuristics. More importantly: the consumer of this product is a maintenance
   planner who must justify spending money on span 0_0020 and not 0_0021.
   A score that decomposes into "62% of the corridor is dense vegetation and
   a third of it greened up sharply since last year" survives that meeting.
   A neural network's logit does not. ML belongs on top of this later, with
   this as its explainable baseline.
4. **QA is the product.** Every check returns a structured result, severities
   have contractual meaning, and the gate physically blocks the delivery
   artifacts from being written. If I only get to show an interviewer one
   file, it is the QA report of a *blocked* run.
5. **Config over code.** Buffer width, span length, thresholds, weights, date
   windows — every number a domain expert might challenge lives in one YAML
   that can be diffed and reviewed. Magic numbers in code are where
   accountability goes to die.

## Open questions (to resolve during implementation)

- Span cutting: what happens to the line remainder < 250 m? (Must not be
  silently dropped — conservation of length should be a unit test.)
- SCL cloud handling: scene-level filter at search time first; per-pixel
  masking is a later iteration, note it as a limitation rather than hiding it.
- No-data spans: deliver as an explicit "no-data" class. A span we could not
  see must never be reported as "low risk" — that is how trust dies.
