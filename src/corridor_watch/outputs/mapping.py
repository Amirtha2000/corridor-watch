"""Interactive delivery map (Folium/Leaflet).

Design goals, in order:
1. Evidence, not just verdicts — the NDVI-change raster is embedded as an
   overlay so a viewer can see the regrowth that triggered each red span.
2. Works offline — the raster overlays are base64-embedded in the HTML, so
   the map still shows the analysis even if basemap tiles cannot load.
3. Readable by non-specialists — popups explain each span in sentences.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import folium
import folium.plugins
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import transform_bounds

_COLORS = {"high": "#d03b3b", "medium": "#ec835a", "low": "#0ca30c", "no-data": "#8a8984"}
_LABELS = {"high": "High risk", "medium": "Medium risk", "low": "Low risk", "no-data": "No data"}


def _raster_overlay_png(path: str | Path, mode: str) -> tuple[str, list[list[float]]]:
    """Render a raster to a base64 PNG + WGS84 bounds for ImageOverlay.

    mode="ndvi":   greenness backdrop (light -> dark green).
    mode="growth": only significant positive change, yellow -> red, transparent elsewhere.
    """
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import cm, colors

    with rasterio.open(path) as src:
        arr = src.read(1)
        s, w_, n, e = None, None, None, None
        w_, s, e, n = transform_bounds(src.crs, "EPSG:4326", *src.bounds)

    if mode == "ndvi":
        norm = colors.Normalize(vmin=0.0, vmax=0.9)
        rgba = cm.get_cmap("YlGn")(norm(np.nan_to_num(arr, nan=0.0)))
        rgba[..., 3] = np.where(np.isfinite(arr), 1.0, 0.0)
    else:  # growth
        norm = colors.Normalize(vmin=0.10, vmax=0.45)
        rgba = cm.get_cmap("YlOrRd")(norm(np.nan_to_num(arr, nan=0.0)))
        visible = np.isfinite(arr) & (arr > 0.10)
        rgba[..., 3] = np.where(visible, 0.85, 0.0)

    buf = io.BytesIO()
    import matplotlib.pyplot as plt

    plt.imsave(buf, rgba, format="png")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}", [[s, w_], [n, e]]


def _popup_html(r) -> str:
    color = _COLORS[r["risk_class"]]
    if r["risk_class"] == "no-data":
        body = "The satellite could not observe this span clearly."
    else:
        body = (
            f"<b>{r['veg_fraction']:.0%}</b> of this corridor span is densely vegetated<br>"
            f"<b>{r['growth_fraction']:.0%}</b> of it grew significantly vs the baseline year<br>"
            f"Peak greenness (NDVI p90): <b>{r['ndvi_p90']:.2f}</b>"
        )
    return (
        f'<div style="font:13px/1.5 \'Helvetica Neue\',Arial,sans-serif; color:#051c2c; min-width:230px">'
        f'<div style="border-left:4px solid {color}; padding-left:10px; margin-bottom:6px">'
        f'<b style="font-size:14px">Span #{int(r["rank"])} &middot; km {r["km_start"]}&ndash;{r["km_end"]}</b><br>'
        f'<span style="color:{color}; font-weight:600">&#9679; {_LABELS[r["risk_class"]]}'
        f' &middot; score {r["risk_score"]:.2f}</span></div>'
        f"{body}</div>"
    )


def write_map(
    scored: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
    out_path: str | Path,
    ndvi_path: str | Path | None = None,
    dndvi_path: str | Path | None = None,
    title: str = "Corridor Watch — vegetation risk",
) -> Path:
    scored_wgs = scored.to_crs("EPSG:4326").copy()
    lines_wgs = lines.to_crs("EPSG:4326")
    scored_wgs["popup_html"] = [_popup_html(r) for _, r in scored_wgs.iterrows()]
    scored_wgs["status"] = scored_wgs["risk_class"].map(_LABELS)

    minx, miny, maxx, maxy = scored_wgs.total_bounds
    m = folium.Map(tiles=None, control_scale=True)
    m.fit_bounds([[miny, minx], [maxy, maxx]], padding=(30, 30))

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics",
        name="Satellite basemap",
    ).add_to(m)
    folium.TileLayer("CartoDB positron", name="Light basemap", show=False).add_to(m)

    # Embedded analysis rasters — visible even with no tile server reachable.
    if ndvi_path and Path(ndvi_path).exists():
        uri, bounds = _raster_overlay_png(ndvi_path, "ndvi")
        folium.raster_layers.ImageOverlay(
            uri, bounds=bounds, opacity=0.75, name="Greenness (NDVI, current)", show=True
        ).add_to(m)
    if dndvi_path and Path(dndvi_path).exists():
        uri, bounds = _raster_overlay_png(dndvi_path, "growth")
        folium.raster_layers.ImageOverlay(
            uri, bounds=bounds, opacity=0.9, name="Significant growth since baseline", show=True
        ).add_to(m)

    folium.GeoJson(
        lines_wgs,
        name="Transmission line",
        style_function=lambda f: {"color": "#051c2c", "weight": 3, "dashArray": "8 5", "opacity": 0.9},
    ).add_to(m)

    def style(feature):
        cls = feature["properties"].get("risk_class", "no-data")
        return {
            "fillColor": _COLORS.get(cls, "#8a8984"),
            "color": "#ffffff",
            "weight": 1.2,
            "fillOpacity": 0.30 if cls == "low" else 0.62,
        }

    folium.GeoJson(
        scored_wgs[["segment_id", "rank", "km_start", "km_end", "status", "risk_score",
                    "risk_class", "popup_html", "geometry"]],
        name="Corridor spans (risk)",
        style_function=style,
        highlight_function=lambda f: {"weight": 3, "color": "#2251ff", "fillOpacity": 0.75},
        tooltip=folium.GeoJsonTooltip(
            fields=["rank", "km_start", "km_end", "status", "risk_score"],
            aliases=["Priority #", "From km", "To km", "Status", "Risk score"],
            sticky=True,
        ),
        popup=folium.GeoJsonPopup(fields=["popup_html"], labels=False),
    ).add_to(m)

    # Priority markers on the top-3 spans so the eye lands somewhere.
    for _, r in scored_wgs[scored_wgs["rank"] <= 3].iterrows():
        c = r.geometry.centroid
        folium.Marker(
            [c.y, c.x],
            icon=folium.DivIcon(html=(
                f'<div style="background:#051c2c;color:#fff;border:2px solid #fff;'
                f'border-radius:50%;width:26px;height:26px;line-height:23px;'
                f'text-align:center;font:700 12px Arial;box-shadow:0 1px 4px rgba(0,0,0,.4)">'
                f'{int(r["rank"])}</div>'
            )),
            tooltip=f"Priority #{int(r['rank'])}: km {r['km_start']}–{r['km_end']}",
        ).add_to(m)

    header = f"""
    <div style="position:fixed; top:12px; left:50%; transform:translateX(-50%); z-index:9999;
                background:#ffffff; border-top:4px solid #051c2c; padding:10px 22px;
                box-shadow:0 1px 6px rgba(0,0,0,.25);
                font-family:'Helvetica Neue',Arial,sans-serif; text-align:center;">
      <div style="font-size:15px; font-weight:700; color:#051c2c">{title}</div>
      <div style="font-size:11.5px; color:#3c4a57; margin-top:2px">
        Click a span for the evidence behind its color &middot; toggle layers top-right
      </div>
    </div>
    <div style="position:fixed; bottom:22px; left:18px; z-index:9999; background:#ffffff;
                padding:10px 14px; border-top:3px solid #051c2c;
                box-shadow:0 1px 6px rgba(0,0,0,.25);
                font:12px/1.7 'Helvetica Neue',Arial,sans-serif; color:#051c2c;">
      <b>Corridor spans</b><br>
      <span style="color:{_COLORS['high']}">&#9632;</span> High — cut this season<br>
      <span style="color:{_COLORS['medium']}">&#9632;</span> Medium — inspect next patrol<br>
      <span style="color:{_COLORS['low']}">&#9632;</span> Low — no action<br>
      <span style="color:{_COLORS['no-data']}">&#9632;</span> No data — verify on ground<br>
      <span style="border-bottom:2px dashed #051c2c">&nbsp;&nbsp;&nbsp;&nbsp;</span> transmission line
    </div>"""
    m.get_root().html.add_child(folium.Element(header))
    folium.LayerControl(collapsed=False).add_to(m)
    folium.plugins.Fullscreen(position="topleft").add_to(m)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    _inline_core_libs(out_path)
    return out_path


_VENDOR = Path(__file__).parent / "vendor"


def _inline_core_libs(html_path: Path) -> None:
    """Embed Leaflet and jQuery into the HTML so the map renders offline.

    Delivery HTML gets opened in review environments with no or restricted
    internet; a map that renders as a blank page there is a support ticket.
    Basemap tiles still need connectivity, but the embedded analysis overlays,
    spans and legend render regardless. Non-core CDN extras (bootstrap,
    awesome-markers) are left as-is — they degrade gracefully.
    """
    html = html_path.read_text()
    replacements = {
        "leaflet.js": ("<script>", "</script>"),
        "jquery": ("<script>", "</script>"),
        "leaflet.css": ("<style>", "</style>"),
    }
    for key, (open_tag, close_tag) in replacements.items():
        asset = {
            "leaflet.js": _VENDOR / "leaflet.js",
            "jquery": _VENDOR / "jquery.min.js",
            "leaflet.css": _VENDOR / "leaflet.css",
        }[key]
        if not asset.exists():
            continue
        content = asset.read_text()
        out_lines = []
        for line in html.splitlines():
            token = line.strip()
            is_script = token.startswith("<script") and "src=" in token and key in token
            is_css = token.startswith("<link") and 'rel="stylesheet"' in token and key in token
            if is_script or is_css:
                out_lines.append(f"{open_tag}\n{content}\n{close_tag}")
            else:
                out_lines.append(line)
        html = "\n".join(out_lines)
    html_path.write_text(html)
