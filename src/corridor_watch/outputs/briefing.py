"""Stakeholder delivery briefing.

The GeoJSON is for QGIS and the map is for analysts — this module produces the
artifact for everyone else: a self-contained HTML briefing that explains, in
plain language, what was monitored, what was found, why it matters, and what
should happen next. Generated fresh with every delivery so the narrative can
never drift out of sync with the data.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd

STATUS = {
    "high": ("#d03b3b", "⛔", "High risk"),
    "medium": ("#ec835a", "⚠️", "Medium risk"),
    "low": ("#0ca30c", "✅", "Low risk"),
    "no-data": ("#8a8984", "◌", "No data"),
}

ACTION = {
    "high": "Schedule vegetation cutting this season",
    "medium": "Add to the next inspection patrol",
    "low": "No action needed this cycle",
    "no-data": "Satellite view obstructed — verify on the ground",
}


def _reason(row) -> str:
    if row["risk_class"] == "no-data":
        return "The satellite could not see this span clearly in the imagery used."
    parts = []
    if row["veg_fraction"] == row["veg_fraction"]:  # not NaN
        parts.append(f"{row['veg_fraction']:.0%} of the corridor here is densely vegetated")
    if row["growth_fraction"] and row["growth_fraction"] == row["growth_fraction"]:
        parts.append(f"{row['growth_fraction']:.0%} of it has visibly grown since the baseline summer")
    return (" and ".join(parts) + ".") if parts else "Vegetation levels are unremarkable."


def _risk_profile_svg(scored: gpd.GeoDataFrame) -> str:
    """Risk score along the line — one thin bar per span, colored by class."""
    df = scored.sort_values("km_start")
    w, h, pad_l, pad_b, pad_t = 860, 180, 46, 30, 14
    plot_w, plot_h = w - pad_l - 12, h - pad_b - pad_t
    km_max = float(df["km_end"].max())
    bars, labels = [], []
    for _, r in df.iterrows():
        x = pad_l + (r["km_start"] / km_max) * plot_w
        bw = max(((r["km_end"] - r["km_start"]) / km_max) * plot_w - 2, 2)  # 2px gap
        bh = max(r["risk_score"] * plot_h, 2)
        y = pad_t + plot_h - bh
        color = STATUS[r["risk_class"]][0]
        tip = (f"km {r['km_start']}–{r['km_end']} · {STATUS[r['risk_class']][2]} · "
               f"score {r['risk_score']:.2f}")
        bars.append(
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
            f'rx="3" fill="{color}"><title>{html.escape(tip)}</title></rect>'
        )
        if r["rank"] <= 3:
            labels.append(
                f'<text x="{x + bw / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
                f'class="lbl">#{int(r["rank"])}</text>'
            )
    ticks = "".join(
        f'<text x="{pad_l + (k / km_max) * plot_w:.1f}" y="{h - 8}" text-anchor="middle" class="tick">km {k:g}</text>'
        for k in [0, round(km_max / 2, 1), round(km_max, 1)]
    )
    grid = "".join(
        f'<line x1="{pad_l}" x2="{w - 12}" y1="{pad_t + plot_h * (1 - v):.1f}" '
        f'y2="{pad_t + plot_h * (1 - v):.1f}" class="grid"/>'
        f'<text x="{pad_l - 6}" y="{pad_t + plot_h * (1 - v) + 4:.1f}" text-anchor="end" class="tick">{v:.1f}</text>'
        for v in (0.0, 0.5, 1.0)
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Risk score along the corridor">'
        f"{grid}{''.join(bars)}{''.join(labels)}{ticks}</svg>"
    )


def write_briefing(
    scored: gpd.GeoDataFrame,
    out_dir: str | Path,
    aoi_name: str,
    baseline_range: list[str],
    monitor_range: list[str],
    qa_json_path: str | Path | None = None,
    map_html_path: str | Path | None = None,
) -> Path:
    out_dir = Path(out_dir)
    df = scored.drop(columns="geometry")
    counts = df["risk_class"].value_counts().to_dict()
    n = len(df)
    n_high, n_med = counts.get("high", 0), counts.get("medium", 0)
    n_nodata = counts.get("no-data", 0)
    total_km = float(df["km_end"].max())
    attention = n_high + n_med
    patrol_saved = 1 - attention / n if n else 0

    verdict = "UNKNOWN"
    if qa_json_path and Path(qa_json_path).exists():
        verdict = json.loads(Path(qa_json_path).read_text()).get("verdict", "UNKNOWN")
    verdict_ok = verdict.startswith("PASS")

    top = scored.sort_values("rank").head(5)
    rows = "".join(
        f"<tr><td><b>#{int(r['rank'])}</b></td>"
        f"<td>km {r['km_start']} – {r['km_end']}</td>"
        f"<td><span class='chip' style='--c:{STATUS[r['risk_class']][0]}'>"
        f"{STATUS[r['risk_class']][1]} {STATUS[r['risk_class']][2]}</span></td>"
        f"<td>{html.escape(_reason(r))}</td>"
        f"<td>{ACTION[r['risk_class']]}</td></tr>"
        for _, r in top.iterrows()
    )

    map_embed = ""
    if map_html_path and Path(map_html_path).exists():
        map_embed = (
            "<h2>Explore the corridor yourself</h2>"
            "<p>Every colored strip below is one 250-metre stretch of the line. "
            "Click any strip to see the evidence behind its color. The dashed black "
            "line is the power line itself.</p>"
            f'<iframe class="map" srcdoc="{html.escape(Path(map_html_path).read_text())}" '
            'loading="lazy" title="Interactive corridor risk map"></iframe>'
        )

    stamp = datetime.now(timezone.utc).strftime("%d %B %Y")
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vegetation risk briefing — {html.escape(aoi_name)}</title>
<style>
  :root {{
    color-scheme: light;
    --surface: #fcfcfb; --card: #ffffff; --line: #e4e3df;
    --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #8a8984;
    --accent: #2a78d6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ color-scheme: dark; --surface:#1a1a19; --card:#232322; --line:#3a3936;
            --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#8a8984; --accent:#3987e5; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--surface); color:var(--ink);
         font:16px/1.6 -apple-system, "Segoe UI", Roboto, sans-serif; }}
  .wrap {{ max-width: 920px; margin: 0 auto; padding: 40px 24px 64px; }}
  h1 {{ font-size: 30px; line-height:1.2; margin: 0 0 4px; }}
  h2 {{ font-size: 20px; margin: 40px 0 8px; }}
  p  {{ color: var(--ink-2); margin: 8px 0; }}
  .sub {{ color: var(--ink-3); font-size: 14px; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
            gap:12px; margin:24px 0; }}
  .tile {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:16px 18px; }}
  .tile .n {{ font-size:30px; font-weight:700; line-height:1.1; }}
  .tile .l {{ font-size:13px; color:var(--ink-2); margin-top:4px; }}
  .chip {{ display:inline-block; padding:2px 10px; border-radius:999px;
           border:1.5px solid var(--c); color:var(--ink); font-size:13px;
           white-space:nowrap; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
           border:1px solid var(--line); border-radius:12px; overflow:hidden;
           font-size:14px; }}
  th, td {{ text-align:left; padding:10px 12px; border-top:1px solid var(--line);
            vertical-align:top; }}
  thead th {{ border-top:none; color:var(--ink-2); font-weight:600;
              background:color-mix(in srgb, var(--card) 60%, var(--surface)); }}
  svg {{ width:100%; height:auto; display:block; background:var(--card);
        border:1px solid var(--line); border-radius:12px; padding:8px; }}
  .grid {{ stroke: var(--line); stroke-width:1; }}
  .tick, .lbl {{ font:12px sans-serif; fill: var(--ink-3); }}
  .lbl {{ font-weight:700; fill: var(--ink); }}
  .bar:hover {{ opacity:.75; }}
  .map {{ width:100%; height:480px; border:1px solid var(--line); border-radius:12px; }}
  .note {{ background:var(--card); border-left:4px solid var(--accent);
           border-radius:0 10px 10px 0; padding:12px 16px; }}
  footer {{ margin-top:48px; color:var(--ink-3); font-size:13px;
            border-top:1px solid var(--line); padding-top:16px; }}
</style></head><body><div class="wrap">

<p class="sub">Corridor Watch · delivery briefing · {stamp}</p>
<h1>Is vegetation threatening this power line?</h1>
<p class="sub">Corridor: {html.escape(aoi_name)} · comparing summer
{html.escape(baseline_range[0][:4])} with summer {html.escape(monitor_range[0][:4])} ·
quality verdict: <span class="chip" style="--c:{'#0ca30c' if verdict_ok else '#d03b3b'}">
{'✅' if verdict_ok else '⛔'} {html.escape(verdict)}</span></p>

<h2>Why anyone should care</h2>
<p>Trees and power lines are a bad combination. A branch touching a high-voltage
conductor can cut electricity to thousands of homes, and in dry weather it can
start a wildfire. Grid operators are therefore legally required to keep a
clearance corridor around every line free of tall vegetation — traditionally by
sending helicopters and foot patrols along thousands of kilometres of line,
most of which turns out to be perfectly fine.</p>
<p class="note">This briefing answers one question with satellite imagery instead:
<b>along these {total_km:.1f} km of line, where exactly is vegetation becoming a
problem — so that a crew is sent only where it is needed?</b></p>

<div class="tiles">
  <div class="tile"><div class="n">{total_km:.1f} km</div><div class="l">of line monitored from space</div></div>
  <div class="tile"><div class="n">{n}</div><div class="l">250 m spans assessed individually</div></div>
  <div class="tile"><div class="n" style="color:#d03b3b">{n_high}</div><div class="l">spans need action this season</div></div>
  <div class="tile"><div class="n">{patrol_saved:.0%}</div><div class="l">of the corridor needs no visit at all</div></div>
</div>

<h2>What we found</h2>
<p>Each span of the corridor was compared against the same stretch one year
earlier. Most of the line is stable: the maintained corridor is doing its job.
But vegetation is clearly advancing back into the corridor in
<b>{n_high + n_med} places</b>{f", and {n_nodata} span(s) could not be assessed and need a ground check" if n_nodata else ""}.
The chart below shows the risk score along the line — taller and redder means
more urgent.</p>
{_risk_profile_svg(scored)}

<h2>Where to send the crew first</h2>
<table>
<thead><tr><th></th><th>Location</th><th>Status</th><th>What the satellite sees</th><th>Recommended action</th></tr></thead>
<tbody>{rows}</tbody>
</table>

{map_embed}

<h2>What this means in practice</h2>
<p>Without this screening, inspecting these {total_km:.1f} km means patrolling all
{n} spans. With it, a crew visits <b>{attention} span(s)</b> — roughly
{patrol_saved:.0%} less ground to cover — and gets there <i>before</i> the next
storm or dry spell turns growth into an outage or an ignition. Because new
satellite imagery arrives every few days, this assessment can be refreshed
continuously rather than once a year.</p>

<h2>What this can and cannot tell you</h2>
<p>The satellite measures how much healthy green vegetation is present and how
much it has grown — it does not measure tree height or the exact distance to
the conductors. Red spans mean "vegetation is advancing here, look closer",
not "a branch is touching the wire". Spans marked "no data" were obscured
(usually by cloud) and are flagged rather than guessed. Every delivery ships
with an automated quality report; if the data behind this briefing had failed
those checks, this document would not exist.</p>

<footer>Data: ESA Copernicus Sentinel-2 imagery (10 m) · line geometry © OpenStreetMap
contributors · analysis: Corridor Watch pipeline. Scores are screening-level
guidance, not a substitute for on-site clearance measurement.</footer>
</div></body></html>"""

    out_path = out_dir / "delivery_briefing.html"
    out_path.write_text(doc)
    return out_path
