"""Command-line entry point.

    corridor-watch demo    --config config/corridor_brandenburg.yaml
    corridor-watch fetch   --config config/corridor_brandenburg.yaml   (needs internet)
    corridor-watch run     --config config/corridor_brandenburg.yaml

``run`` executes: NDVI + change → corridor segmentation → QA gates →
risk scoring → delivery outputs (GeoJSON, CSV, interactive map, QA report).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from corridor_watch import qa
from corridor_watch.analysis import corridor, indices, risk
from corridor_watch.config import Config, load_config

log = logging.getLogger("corridor_watch")


def _write_raster(arr: np.ndarray, like_path: Path, out_path: Path) -> Path:
    with rasterio.open(like_path) as like:
        profile = like.profile | {"dtype": "float32", "count": 1, "compress": "deflate"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)
    return out_path


def cmd_demo(cfg: Config) -> None:
    from corridor_watch import demo

    demo.generate(cfg, cfg.path("raw_dir"))
    log.info("Demo data ready in %s — now run: corridor-watch run", cfg.path("raw_dir"))


def cmd_fetch(cfg: Config) -> None:
    from corridor_watch.fetch import osm, stac

    img = cfg.raw["imagery"]
    infra = cfg.raw["infrastructure"]
    raw_dir = cfg.path("raw_dir")

    lines = osm.fetch_power_lines(infra["overpass_api"], cfg.bbox, infra["min_voltage_kv"])
    lines.to_file(raw_dir / "power_lines.geojson", driver="GeoJSON")

    for label, date_key in [("baseline", "baseline_date_range"), ("monitor", "monitor_date_range")]:
        items = stac.search_scenes(
            img["stac_api"], img["collection"], cfg.bbox, tuple(img[date_key]), img["max_cloud_cover"]
        )
        best = items[0]
        log.info("%s epoch: %s (%.1f%% cloud)", label, best.id, best.properties.get("eo:cloud_cover", -1))
        stac.download_subset(best, img["bands"], cfg.bbox, cfg.crs_utm, raw_dir, label)


def cmd_run(cfg: Config, override_qa: bool = False) -> int:
    raw_dir, proc_dir, out_dir = cfg.path("raw_dir"), cfg.path("processed_dir"), cfg.path("outputs_dir")
    qa_results: list[qa.CheckResult] = []

    # 1 — load inputs
    lines = gpd.read_file(raw_dir / "power_lines.geojson")
    qa_results += qa.run_vector_checks(lines, "input power lines", expected_crs="EPSG:4326")

    # 2 — NDVI per epoch + change
    ndvi_paths: dict[str, Path] = {}
    for label in ("baseline", "monitor"):
        with rasterio.open(raw_dir / f"{label}_red.tif") as r, rasterio.open(raw_dir / f"{label}_nir.tif") as n:
            arr = indices.ndvi(r.read(1), n.read(1))
        ndvi_paths[label] = _write_raster(arr, raw_dir / f"{label}_red.tif", proc_dir / f"ndvi_{label}.tif")

    with rasterio.open(ndvi_paths["baseline"]) as b, rasterio.open(ndvi_paths["monitor"]) as m:
        dndvi = indices.delta(b.read(1), m.read(1))
    dndvi_path = _write_raster(dndvi, ndvi_paths["baseline"], proc_dir / "dndvi.tif")

    # 3 — QA gate on rasters (block bad data before it becomes a delivery)
    for label, path in [*ndvi_paths.items(), ("dNDVI", dndvi_path)]:
        valid_range = tuple(cfg.qa["ndvi_valid_range"]) if label != "dNDVI" else (-2.0, 2.0)
        qa_results += qa.run_raster_checks(
            str(path), f"NDVI {label}" if label != "dNDVI" else "dNDVI",
            expected_crs=cfg.crs_utm, valid_range=valid_range,
            max_nodata_fraction=cfg.qa["max_nodata_fraction"],
        )

    # 4 — corridor segmentation + scoring
    segments = corridor.segment_lines(lines, cfg.segment_length_m, cfg.crs_utm)
    corridors = corridor.buffer_segments(segments, cfg.buffer_m)
    qa_results += qa.run_vector_checks(
        corridors, "corridor segments", expected_crs=cfg.crs_utm, min_features=cfg.qa["min_segments"]
    )

    scored = risk.zonal_stats(
        corridors, str(ndvi_paths["monitor"]), str(dndvi_path),
        cfg.veg_threshold, cfg.growth_threshold,
    )
    scored = risk.score(scored, cfg.risk_weights, cfg.risk_thresholds)
    qa_results += qa.run_output_checks(scored, cfg.qa["min_segments"])

    # 5 — QA report, then gate
    context = {
        "config": cfg.source_path.name if cfg.source_path else "unknown",
        "aoi": cfg.raw["aoi"]["name"],
        "segments": len(scored),
        "high_risk": int((scored["risk_class"] == "high").sum()),
    }
    md_path, json_path = qa.write_report(qa_results, out_dir, cfg.raw["aoi"]["name"], context)
    log.info("QA report: %s", md_path)
    try:
        qa.gate(qa_results, fail_on=tuple(cfg.qa["fail_on"]))
    except qa.checks.QAGateError:
        if not override_qa:
            log.error("QA gate failed — outputs withheld. Re-run with --override-qa to force.")
            raise
        log.warning("QA gate failed but --override-qa set: delivering flagged outputs.")

    # 6 — deliverables
    out_dir.mkdir(parents=True, exist_ok=True)
    scored.to_file(out_dir / "corridor_risk.geojson", driver="GeoJSON")
    scored.drop(columns="geometry").to_csv(out_dir / "corridor_risk.csv", index=False)

    from corridor_watch.outputs import mapping

    map_path = mapping.write_map(
        scored, lines.to_crs(cfg.crs_utm), out_dir / "corridor_risk_map.html",
        ndvi_path=ndvi_paths["monitor"], dndvi_path=dndvi_path,
    )

    from corridor_watch.outputs import briefing

    img = cfg.raw.get("imagery", {})
    briefing_path = briefing.write_briefing(
        scored, out_dir, cfg.raw["aoi"]["name"],
        img.get("baseline_date_range", ["", ""]), img.get("monitor_date_range", ["", ""]),
        qa_json_path=json_path, map_html_path=map_path,
    )

    top = scored.head(5)[["rank", "segment_id", "km_start", "km_end", "risk_class", "risk_score"]]
    log.info("Top risk spans:\n%s", top.to_string(index=False))
    log.info(
        "Delivery complete → %s | %s | %s | %s",
        "corridor_risk.geojson", "corridor_risk.csv", map_path.name, briefing_path.name,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corridor-watch", description=__doc__)
    parser.add_argument("command", choices=["demo", "fetch", "run"])
    parser.add_argument("--config", default="config/corridor_brandenburg.yaml")
    parser.add_argument("--override-qa", action="store_true",
                        help="deliver outputs even if blocking QA checks fail (flagged in report)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_config(args.config)

    if args.command == "demo":
        cmd_demo(cfg)
    elif args.command == "fetch":
        cmd_fetch(cfg)
    else:
        return cmd_run(cfg, override_qa=args.override_qa)
    return 0


if __name__ == "__main__":
    sys.exit(main())
