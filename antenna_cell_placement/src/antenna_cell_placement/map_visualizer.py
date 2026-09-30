"""
Interactive Leaflet/Folium geospatial visualization for Libyan cell sites and AI placement recommendations.
"""

from pathlib import Path
from html import escape
import folium
from folium.plugins import MarkerCluster, FeatureGroupSubGroup
import pandas as pd
import geopandas as gpd

from antenna_cell_placement.config import (
    CLEANED_PHYSICAL_SITES_CSV,
    RECOMMENDATIONS_CSV,
    CLEANED_MAP_HTML,
    REPORTS_DIR,
    ADMIN1_GEOJSON_PATH,
    ROADS_SHP_PATH,
    POP_PLACES_GEOJSON_PATH,
    CRS_PROJECTED_LIBYA,
)


def add_local_basemap(m: folium.Map):
    """Embed geographic context without requests to a public tile server."""
    boundaries = gpd.read_file(ADMIN1_GEOJSON_PATH)[["adm1_name", "geometry"]]
    boundaries = boundaries.to_crs(CRS_PROJECTED_LIBYA)
    boundaries.geometry = boundaries.geometry.simplify(150, preserve_topology=True)
    base = folium.FeatureGroup(name="Libya boundaries (embedded)", overlay=False)
    folium.GeoJson(
        boundaries.to_crs("EPSG:4326").to_json(),
        style_function=lambda _: {
            "color": "#94a3b8", "weight": 1.5,
            "fillColor": "#f5f1e7", "fillOpacity": 1,
        },
        interactive=False,
    ).add_to(base)
    base.add_to(m)

    roads = gpd.read_file(ROADS_SHP_PATH)[["geometry"]].to_crs(CRS_PROJECTED_LIBYA)
    roads.geometry = roads.geometry.simplify(100, preserve_topology=True)
    road_layer = folium.FeatureGroup(name="Road network (embedded)")
    folium.GeoJson(
        roads.to_crs("EPSG:4326").to_json(),
        style_function=lambda _: {"color": "#c49553", "weight": 1.2, "opacity": 0.7},
        interactive=False,
    ).add_to(road_layer)
    road_layer.add_to(m)

    places = gpd.read_file(POP_PLACES_GEOJSON_PATH).to_crs("EPSG:4326")
    settlements = folium.FeatureGroup(name="Settlement labels (embedded)")
    for _, place in places.iterrows():
        name = escape(str(place["featurename_en"]))
        folium.Marker(
            [place.geometry.y, place.geometry.x],
            icon=folium.DivIcon(
                html=f'<span class="settlement-label">{name}</span>',
                icon_size=(150, 16), icon_anchor=(-5, 8),
            ),
        ).add_to(settlements)
    settlements.add_to(m)
    m.get_root().header.add_child(folium.Element('''<style>
        .leaflet-container { background: #dcecf2 !important; }
        .settlement-label { font: 11px Arial, sans-serif; color: #334155;
            white-space: nowrap; text-shadow: 1px 1px white, -1px -1px white,
            1px -1px white, -1px 1px white; }
    </style>'''))
    m.get_root().html.add_child(folium.Element('''
        <div style="position:fixed;bottom:5px;left:10px;z-index:9999;
                    background:white;padding:4px;font:11px Arial,sans-serif">
        Embedded basemap: UN OCHA boundaries, roads and settlements.
        No map tile service required.</div>'''))


def generate_interactive_map(
    sites_csv: Path = CLEANED_PHYSICAL_SITES_CSV,
    recommendations_csv: Path = RECOMMENDATIONS_CSV,
    output_html: Path = CLEANED_MAP_HTML,
    report_html: Path = REPORTS_DIR / "libya_cell_coverage_map.html"
) -> Path:
    """
    Generates high-performance interactive Leaflet HTML maps displaying:
    - Cleaned existing physical cell sites (color-coded by technology and operator)
    - AI-recommended new cell site placements with popup intelligence
    """
    print("Loading cleaned physical sites and AI recommendations...")
    df_sites = pd.read_csv(sites_csv)
    df_recs = pd.read_csv(recommendations_csv) if recommendations_csv.exists() else None

    from antenna_cell_placement.config import OPENCELLID_RAW_PATH
    from antenna_cell_placement.opencellid import load_cells, annotate_candidates
    cells = None
    if OPENCELLID_RAW_PATH.exists():
        cells, _, _ = load_cells(OPENCELLID_RAW_PATH)
        if df_recs is not None:
            df_recs = annotate_candidates(df_recs, cells)

    # Center map on Libya
    center_lat = 30.5
    center_lon = 17.5
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles=None,
        control_scale=True
    )
    add_local_basemap(m)

    m.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;top:10px;left:50px;z-index:9999;background:white;padding:10px;max-width:420px">'
        '<b>Planning priorities for engineering review</b><br>'
        'Experimental existing-site pattern recognition; not RF coverage or deployment approval. '
        'Building heights unavailable. Equipment and spectrum require engineering evidence.</div>'))

    # 1. Feature Groups for Existing Sites
    fg_lte = folium.FeatureGroup(name="4G LTE Sites (Existing)")
    fg_multitech = folium.FeatureGroup(name="Multi-Technology Co-sited (Existing)")
    fg_umts = folium.FeatureGroup(name="3G UMTS / HSPA+ (Existing)")
    fg_gsm = folium.FeatureGroup(name="2G GSM / EDGE (Existing)")

    for _, row in df_sites.iterrows():
        lat = row["canonical_latitude"]
        lon = row["canonical_longitude"]
        techs = str(row["technologies"])
        ops = str(row["operators"])
        bw = row.get("total_bandwidth_mhz", 0.0)
        pop_1k = row.get("population_density_1km", 0.0)
        elev = row.get("elevation_m", 0.0)

        # Style by technology
        if row.get("is_multi_tech", 0) == 1:
            color = "#2563eb"  # Blue
            target_fg = fg_multitech
            icon_name = "tower-broadcast"
        elif "LTE" in techs:
            color = "#16a34a"  # Green
            target_fg = fg_lte
            icon_name = "signal"
        elif "UMTS" in techs:
            color = "#9333ea"  # Purple
            target_fg = fg_umts
            icon_name = "wifi"
        else:
            color = "#f59e0b"  # Amber
            target_fg = fg_gsm
            icon_name = "broadcast-tower"

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 200px;">
            <h4 style="margin: 0 0 6px; color: #1e293b;">Physical Site #{row['physical_site_id']}</h4>
            <p style="margin: 2px 0;"><b>Technologies:</b> {techs}</p>
            <p style="margin: 2px 0;"><b>Operators:</b> {ops}</p>
            <p style="margin: 2px 0;"><b>Antennas:</b> {row['radio_tower_count']}</p>
            <p style="margin: 2px 0;"><b>Coordinates:</b> {lat:.4f}, {lon:.4f}</p>
        </div>
        """

        folium.CircleMarker(
            location=[lat, lon],
            radius=4.5,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"Site #{row['physical_site_id']} ({techs}) - {ops}"
        ).add_to(target_fg)

    fg_multitech.add_to(m)
    fg_lte.add_to(m)
    fg_umts.add_to(m)
    fg_gsm.add_to(m)

    if cells is not None:
        for operator, subset in cells.groupby("operator"):
            layer = folium.FeatureGroup(name=f"OpenCellID estimates: {operator}", show=False)
            cluster = MarkerCluster().add_to(layer)
            for _, cell in subset.iterrows():
                popup = (
                    f"<b>OpenCellID estimated cell — {escape(operator)}</b><br>"
                    f"{escape(cell['radio'])}; area {cell['area']}; cell {cell['cell']}<br>"
                    f"Measurements: {cell['samples']}<br>Last observed: {cell['updated_utc']}<br>"
                    f"Source estimated range: {cell['range']} m<br>"
                    "Estimated cell location; not a verified mast or coverage footprint."
                )
                folium.Marker([cell['lat'], cell['lon']], popup=folium.Popup(popup, max_width=320),
                              tooltip=f"OpenCellID: {operator} {cell['radio']}").add_to(cluster)
            layer.add_to(m)
        m.get_root().html.add_child(folium.Element(
            '<div style="position:fixed;bottom:25px;left:10px;z-index:9999;background:white;padding:5px">'
            'Cell observations: <a href="https://opencellid.org/">OpenCellID</a></div>'
        ))

    # 2. Feature Group for AI Placement Recommendations
    if df_recs is not None and not df_recs.empty:
        fg_recs = folium.FeatureGroup(name="⭐ Planning priorities for engineering review")

        for _, row in df_recs.iterrows():
            lat = row["canonical_latitude"]
            lon = row["canonical_longitude"]
            rank = row["recommendation_rank"]
            muni = row["municipality_name"]
            place = row["nearest_settlement_name"]
            score = row["placement_suitability_score"]
            pop_5k = row["population_sum_5km"]
            gap_m = row["dist_to_nearest_site_m"]
            p_score = row["deployment_priority_score"]

            review_text = ""
            if "opencellid_review_required" in row:
                distance = row.get("opencellid_recent_distance_m")
                proximity = f"{distance / 1000:.2f} km" if pd.notna(distance) else "No eligible observations"
                status = "Review nearby cell evidence" if row['opencellid_review_required'] else "No recent cell within 3 km; coverage unverified"
                review_text = f"<p><b>OpenCellID:</b> {proximity}. {status}.</p>"
            radar_text = ""
            if row.get("cloudflare_data_available", False):
                radar_text = (
                    "<p><b>Cloudflare regional demand:</b> "
                    f"{row['cloudflare_http_requests_share_52w_pct']:.3f}% of 52-week "
                    f"HTTP requests (priority factor {row['cloudflare_priority_factor']:.3f}).</p>"
                )
            rec_popup = f"""
            <div style="font-family: Arial, sans-serif; min-width: 250px;">
                <div style="background: #dc2626; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;">
                    ⭐ Engineering-review priority rank #{rank}
                </div>
                <p style="margin: 6px 0 3px;"><b>Municipality:</b> {muni} ({place})</p>
                <p style="margin: 3px 0;"><b>Experimental site-pattern score:</b> <span style="color: #16a34a; font-weight: bold;">{score:.4f}</span></p>
                <p style="margin: 3px 0;"><b>Priority Score:</b> {p_score}</p>
                <p style="margin: 3px 0;"><b>Population within 5 km (legacy estimate):</b> {int(pop_5k):,} people</p>
                <p style="margin: 3px 0;"><b>Nearest known-site distance:</b> {gap_m / 1000.0:.2f} km</p>
                {radar_text}
                {review_text}
                <p style="margin: 3px 0;"><b>Coordinates:</b> {lat:.4f}, {lon:.4f}</p>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color="#b91c1c",
                weight=2.5,
                fill=True,
                fill_color="#ef4444",
                fill_opacity=0.9,
                popup=folium.Popup(rec_popup, max_width=320),
                tooltip=f"Rank #{rank}: {muni} ({place}) - Score: {score:.2f}"
            ).add_to(fg_recs)

        fg_recs.add_to(m)

    # Layer control
    folium.LayerControl(collapsed=False).add_to(m)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    m.save(output_html)
    print(f"Saved interactive map to: {output_html}")

    report_html.parent.mkdir(parents=True, exist_ok=True)
    m.save(report_html)
    print(f"Saved interactive master report map to: {report_html}")

    return output_html


def generate_h3_expansion_map(city: str = None, top_n: int = 20,
                              source_geojson: Path = None, output_html: Path = None) -> Path:
    """
    Choropleth of per-hex expansion priority for a pilot city, with existing sites
    overlaid and the top-N hexes called out by rank. Uses the embedded basemap.
    """
    import numpy as np
    from antenna_cell_placement.config import (
        DEFAULT_PILOT_CITY,
        PILOT_CITY_BBOXES,
        H3_EXPANSION_SCORE_GEOJSON_TEMPLATE,
        H3_EXPANSION_MAP_HTML_TEMPLATE,
    )

    city = city or DEFAULT_PILOT_CITY
    geojson_path = source_geojson or H3_EXPANSION_SCORE_GEOJSON_TEMPLATE.format(city=city)
    print(f"Loading scored H3 hexes: {geojson_path}")
    gdf = gpd.read_file(geojson_path)

    score_col = "combined_priority_score" if "combined_priority_score" in gdf.columns else "expansion_need_score"
    gdf = gdf.loc[gdf[score_col].notna()].copy()
    if gdf.empty:
        raise ValueError("No scored planning areas are available for this map")
    bins = np.quantile(gdf[score_col], [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    colors = ["#fef0d9", "#fdcc8a", "#fc8d59", "#e34a33", "#b30000"]

    def color_for(value):
        idx = int(np.searchsorted(bins[1:-1], value, side="right"))
        return colors[min(idx, len(colors) - 1)]

    bbox = PILOT_CITY_BBOXES[city]
    center = [(bbox["min_lat"] + bbox["max_lat"]) / 2, (bbox["min_lon"] + bbox["max_lon"]) / 2]
    m = folium.Map(location=center, zoom_start=11, tiles=None, control_scale=True)
    add_local_basemap(m)

    tooltip_fields = [
        ("expansion_rank", "Rank"),
        (score_col, "Priority score"),
        ("expansion_need_score", "GIS planning index"),
        ("placement_suitability_score", "Experimental site-pattern score"),
        ("population_sum_5km", "Population within 5 km"),
        ("existing_sites_site_count", "Existing sites in hex"),
        ("building_count", "Buildings"),
        ("landcover_builtup_pct", "Built-up %"),
        ("osm_road_density_km_per_km2", "Road density (km/km2)"),
        ("poi_count", "POIs"),
        ("h3_index", "H3 index"),
    ]
    tooltip_fields = [(f, a) for f, a in tooltip_fields if f in gdf.columns]
    layer_gdf = gdf[[f for f, _ in tooltip_fields] + ["geometry"]].copy()
    for f, _ in tooltip_fields:
        if layer_gdf[f].dtype.kind == "f":
            layer_gdf[f] = layer_gdf[f].round(2)
        layer_gdf[f] = layer_gdf[f].astype(object).where(layer_gdf[f].notna(), "Unavailable")

    fg_hex = folium.FeatureGroup(name=f"Planning priorities for engineering review ({city})")
    folium.GeoJson(
        layer_gdf.to_json(),
        style_function=lambda feature: {
            "fillColor": color_for(feature["properties"][score_col]),
            "color": "#475569",
            "weight": 0.4,
            "fillOpacity": 0.65,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[f for f, _ in tooltip_fields],
            aliases=[a for _, a in tooltip_fields],
            localize=True,
        ),
    ).add_to(fg_hex)
    fg_hex.add_to(m)

    df_sites = pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)
    df_sites = df_sites[
        df_sites["canonical_latitude"].between(bbox["min_lat"], bbox["max_lat"])
        & df_sites["canonical_longitude"].between(bbox["min_lon"], bbox["max_lon"])
    ]
    fg_sites = folium.FeatureGroup(name="Existing physical sites")
    for _, row in df_sites.iterrows():
        folium.CircleMarker(
            location=[row["canonical_latitude"], row["canonical_longitude"]],
            radius=2.5, color="#1d4ed8", fill=True, fill_color="#1d4ed8", fill_opacity=0.9,
            tooltip=f"Site #{row['physical_site_id']} ({row['technologies']}) - {row['operators']}",
        ).add_to(fg_sites)
    fg_sites.add_to(m)

    top = gdf.sort_values(score_col, ascending=False).head(top_n)
    fg_top = folium.FeatureGroup(name=f"Top {top_n} priority hexes")
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _: {"fillOpacity": 0, "color": "#111827", "weight": 2.5},
        ).add_to(fg_top)
        centroid = row.geometry.centroid
        folium.Marker(
            [centroid.y, centroid.x],
            icon=folium.DivIcon(
                html=f'<div style="font:bold 11px Arial;color:#111827;background:white;'
                     f'border:1px solid #111827;border-radius:8px;padding:0 4px;display:inline-block">#{rank}</div>',
                icon_size=(30, 16), icon_anchor=(15, 8),
            ),
            tooltip=f"Rank #{rank}: {score_col} = {row[score_col]:.2f}",
        ).add_to(fg_top)
    fg_top.add_to(m)

    legend_rows = "".join(
        f'<div><span style="display:inline-block;width:14px;height:12px;background:{colors[i]};'
        f'border:1px solid #94a3b8;margin-right:6px"></span>{bins[i]:.1f} - {bins[i + 1]:.1f}</div>'
        for i in range(len(colors))
    )
    m.get_root().html.add_child(folium.Element(
        f'<div style="position:fixed;top:10px;left:55px;z-index:9999;background:white;'
        f'padding:8px;font:12px Arial,sans-serif;border:1px solid #94a3b8">'
        f'<b>{city}: planning priorities for engineering review</b><br>'
        f'Relative index; experimental ML influences rank. Not RF coverage.<br>'
        f'Building heights unavailable. Score bands (relative index):<br>{legend_rows}</div>'
    ))
    folium.LayerControl(collapsed=False).add_to(m)

    out_path = Path(output_html or H3_EXPANSION_MAP_HTML_TEMPLATE.format(city=city))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(out_path)
    print(f"Saved H3 expansion map to: {out_path}")
    return out_path


def generate_release_map(run_dir: Path, output_html: Path, city: str = "Tripoli") -> Path:
    """Full planning map for a completed integrated run: the H3 map's layout, current data.

    Draws every candidate hexagon (eligible ones by explainable score, rejected ones grey
    with their rejection reason), every reconciled existing site by operator, the ranked
    shortlist and the rooftop footprints, on the same embedded offline basemap as
    `generate_h3_expansion_map`. Reads only the run's own outputs, so it shows exactly
    what that run decided; it never rescores anything.
    """
    import json

    import h3
    import numpy as np
    from shapely.geometry import Polygon

    from antenna_cell_placement.config import PILOT_CITY_BBOXES

    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed":
        raise ValueError(f"{run_dir} is not a completed planning run")
    candidates = pd.read_csv(run_dir / "candidates.csv", low_memory=False)
    shortlist = pd.read_csv(run_dir / "shortlist.csv").sort_values("recommendation_rank")
    sites = pd.read_csv(run_dir / "physical_sites.csv")
    bbox = PILOT_CITY_BBOXES[city]
    center = [(bbox["min_lat"] + bbox["max_lat"]) / 2, (bbox["min_lon"] + bbox["max_lon"]) / 2]
    m = folium.Map(location=center, zoom_start=11, tiles=None, control_scale=True)
    add_local_basemap(m)

    candidates["geometry"] = [
        Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)]) for cell in candidates["h3_index"]
    ]
    rank_by_id = dict(zip(shortlist["candidate_id"], shortlist["recommendation_rank"]))
    candidates["rank"] = candidates["candidate_id"].map(rank_by_id)
    eligible = candidates["eligible"].fillna(False).astype(bool)

    scores = candidates.loc[eligible, "planning_priority_score"]
    bins = np.quantile(scores, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    colors = ["#fef0d9", "#fdcc8a", "#fc8d59", "#e34a33", "#b30000"]

    def color_for(value):
        return colors[min(int(np.searchsorted(bins[1:-1], value, side="right")), len(colors) - 1)]

    def hex_layer(rows, name, fields, style, show=True):
        layer = gpd.GeoDataFrame(rows[[f for f, _ in fields] + ["geometry"]].copy(), crs="EPSG:4326")
        for field, _ in fields:
            if layer[field].dtype.kind == "f":
                layer[field] = layer[field].round(1)
            layer[field] = layer[field].astype(object).where(layer[field].notna(), "-")
        group = folium.FeatureGroup(name=name, show=show)
        folium.GeoJson(
            layer.to_json(), style_function=style,
            tooltip=folium.GeoJsonTooltip(fields=[f for f, _ in fields], aliases=[a for _, a in fields], localize=True),
        ).add_to(group)
        group.add_to(m)

    candidates["nearest_site_km"] = (candidates["dist_to_nearest_site_m"] / 1000).round(1)
    hex_layer(
        candidates.loc[eligible],
        f"Eligible candidates by planning score ({int(eligible.sum())})",
        [("rank", "Shortlist rank"), ("planning_priority_score", "Planning score"),
         ("municipality_name", "Area"), ("reason_codes", "Reasons"),
         ("population_sum_5km", "People within 5 km"), ("nearest_site_km", "Nearest existing site (km)"),
         ("dist_to_nearest_road_m", "Nearest road (m)"), ("h3_index", "H3 cell")],
        lambda f: {"fillColor": color_for(f["properties"]["planning_priority_score"]),
                   "color": "#475569", "weight": 0.4, "fillOpacity": 0.7},
    )
    hex_layer(
        candidates.loc[~eligible],
        f"Rejected candidates ({int((~eligible).sum())})",
        [("municipality_name", "Area"), ("rejection_reasons", "Rejected because"),
         ("nearest_site_km", "Nearest existing site (km)"), ("dist_to_nearest_road_m", "Nearest road (m)"),
         ("h3_index", "H3 cell")],
        lambda f: {"fillColor": "#cbd5e1", "color": "#94a3b8", "weight": 0.3, "fillOpacity": 0.35},
    )

    in_area = sites[
        sites["canonical_latitude"].between(bbox["min_lat"], bbox["max_lat"])
        & sites["canonical_longitude"].between(bbox["min_lon"], bbox["max_lon"])
    ]
    operator_groups = [
        ("Libyana", in_area["has_libyana"] & ~in_area["has_almadar"], "#059669"),
        ("Al-Madar", in_area["has_almadar"] & ~in_area["has_libyana"], "#1d4ed8"),
        ("both operators", in_area["has_almadar"] & in_area["has_libyana"], "#7c3aed"),
    ]
    for label, mask, color in operator_groups:
        group = folium.FeatureGroup(name=f"Existing sites: {label} ({int(mask.sum())})")
        for _, row in in_area.loc[mask].iterrows():
            conflict = " - location conflict in sources" if row["location_conflict"] else ""
            folium.CircleMarker(
                location=[row["canonical_latitude"], row["canonical_longitude"]],
                radius=3, color=color, fill=True, fill_color=color, fill_opacity=0.9, weight=1,
                tooltip=f"Existing site {row['physical_site_id']}: {label}, "
                        f"{int(row['radio_tower_count'])} radio record(s){conflict}",
            ).add_to(group)
        group.add_to(m)

    rooftops = run_dir / "rooftop_candidates.geojson"
    if rooftops.exists():
        footprints = folium.FeatureGroup(name="Building footprints for review", show=False)
        folium.GeoJson(
            rooftops.read_text(encoding="utf-8"),
            style_function=lambda _: {"color": "#0f172a", "weight": 1, "fillColor": "#facc15", "fillOpacity": 0.8},
        ).add_to(footprints)
        footprints.add_to(m)

    top = candidates.loc[candidates["rank"].notna()].sort_values("rank")
    fg_top = folium.FeatureGroup(name=f"Shortlist: top {len(top)} for engineering review")
    for _, row in top.iterrows():
        folium.GeoJson(
            row["geometry"].__geo_interface__,
            style_function=lambda _: {"fillOpacity": 0, "color": "#111827", "weight": 2.5},
        ).add_to(fg_top)
        folium.Marker(
            [row["canonical_latitude"], row["canonical_longitude"]],
            icon=folium.DivIcon(
                html=f'<div style="font:bold 11px Arial;color:#111827;background:white;'
                     f'border:1px solid #111827;border-radius:8px;padding:0 4px;display:inline-block">#{int(row["rank"])}</div>',
                icon_size=(30, 16), icon_anchor=(15, 8),
            ),
            tooltip=f"Rank #{int(row['rank'])} - {row['municipality_name']}: score "
                    f"{row['planning_priority_score']:.1f} ({str(row['reason_codes']).replace(';', ', ')})",
        ).add_to(fg_top)
    fg_top.add_to(m)

    legend_rows = "".join(
        f'<div><span style="display:inline-block;width:14px;height:12px;background:{colors[i]};'
        f'border:1px solid #94a3b8;margin-right:6px"></span>{bins[i]:.1f} - {bins[i + 1]:.1f}</div>'
        for i in range(len(colors))
    )
    site_rows = "".join(
        f'<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background:{color};margin-right:6px"></span>Existing site: {label}</div>'
        for label, _, color in operator_groups
    )
    m.get_root().html.add_child(folium.Element(
        f'<div style="position:fixed;top:10px;left:55px;z-index:9999;background:white;max-width:330px;'
        f'padding:8px;font:12px Arial,sans-serif;border:1px solid #94a3b8">'
        f'<b>{city}: full planning map</b><br>'
        f'Run {run_dir.name} ({manifest["created_utc"][:10]}), inventory {sites["inventory_version"].iloc[0]}.<br>'
        f'{len(candidates):,} candidates, {int(eligible.sum())} eligible, {len(top)} shortlisted; '
        f'{len(in_area):,} existing sites in view.<br>'
        f'Explainable planning score (40% demand, 30% gap to existing sites, 20% road access, '
        f'10% terrain); no ML in the ranking. Not RF coverage. Building heights unavailable.<br>'
        f'Eligible candidates, score bands:<br>{legend_rows}'
        f'<div><span style="display:inline-block;width:14px;height:12px;background:#cbd5e1;'
        f'border:1px solid #94a3b8;margin-right:6px"></span>Rejected (hover for the reason)</div>'
        f'{site_rows}</div>'
    ))
    folium.LayerControl(collapsed=False).add_to(m)

    out_path = Path(output_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(out_path)
    return out_path


if __name__ == "__main__":
    generate_interactive_map()
