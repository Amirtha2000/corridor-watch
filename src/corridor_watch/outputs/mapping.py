"""Interactive delivery map (Folium/Leaflet).

One self-contained HTML file a Project Manager can open in a browser and a
customer can click through: risk-colored corridor spans, the line route,
and a popup per span with the drivers behind its score.
"""
from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd

_COLORS = {"high": "#d7301f", "medium": "#fc8d59", "low": "#2b8cbe", "no-data": "#969696"}


def write_map(
    scored: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
    out_path: str | Path,
    title: str = "Corridor Watch — vegetation risk",
) -> Path:
    scored_wgs = scored.to_crs("EPSG:4326")
    lines_wgs = lines.to_crs("EPSG:4326")

    center = scored_wgs.geometry.union_all().centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=13, tiles="CartoDB positron")

    folium.GeoJson(
        lines_wgs,
        name="Transmission line",
        style_function=lambda f: {"color": "#252525", "weight": 2.5, "dashArray": "6 4"},
    ).add_to(m)

    def style(feature):
        cls = feature["properties"].get("risk_class", "no-data")
        return {
            "fillColor": _COLORS.get(cls, "#969696"),
            "color": _COLORS.get(cls, "#969696"),
            "weight": 1,
            "fillOpacity": 0.55,
        }

    fields = ["rank", "segment_id", "km_start", "km_end", "risk_class", "risk_score",
              "veg_fraction", "growth_fraction", "ndvi_p90", "valid_fraction"]
    fields = [f for f in fields if f in scored_wgs.columns]
    folium.GeoJson(
        scored_wgs,
        name="Corridor segments",
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=fields, sticky=True),
        popup=folium.GeoJsonPopup(fields=fields),
    ).add_to(m)

    legend = f"""
    <div style="position: fixed; bottom: 24px; left: 24px; z-index: 9999;
                background: white; padding: 10px 14px; border-radius: 8px;
                box-shadow: 0 1px 4px rgba(0,0,0,.3); font: 13px/1.5 sans-serif;">
      <b>{title}</b><br>
      <span style="color:{_COLORS['high']}">&#9632;</span> high risk &nbsp;
      <span style="color:{_COLORS['medium']}">&#9632;</span> medium &nbsp;
      <span style="color:{_COLORS['low']}">&#9632;</span> low &nbsp;
      <span style="color:{_COLORS['no-data']}">&#9632;</span> no data
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl().add_to(m)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return out_path
