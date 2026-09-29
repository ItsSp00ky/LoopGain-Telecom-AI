"""Interactive review map for source sites and proposed placements."""

import json
from html import escape
from pathlib import Path

import folium
from folium.plugins import MarkerCluster
import geopandas as gpd
import h3
import pandas as pd

from antenna_cell_placement.config import (
    ADMIN1_GEOJSON_PATH,
    CRS_PROJECTED_LIBYA,
    POP_PLACES_GEOJSON_PATH,
    RECOMMENDATIONS_CSV,
    RECOMMENDATIONS_MAP_HTML,
    ROADS_SHP_PATH,
)


def add_local_basemap(map_: folium.Map) -> None:
    """Embed geographic context without a public tile-server dependency."""
    boundaries = gpd.read_file(ADMIN1_GEOJSON_PATH)[["adm1_name", "geometry"]]
    boundaries = boundaries.to_crs(CRS_PROJECTED_LIBYA)
    boundaries.geometry = boundaries.geometry.simplify(150, preserve_topology=True)
    base = folium.FeatureGroup(name="Libya boundaries (embedded)", overlay=False)
    folium.GeoJson(
        boundaries.to_crs("EPSG:4326").to_json(),
        style_function=lambda _: {
            "color": "#94a3b8",
            "weight": 1.5,
            "fillColor": "#f5f1e7",
            "fillOpacity": 1,
        },
        interactive=False,
    ).add_to(base)
    base.add_to(map_)

    roads = gpd.read_file(ROADS_SHP_PATH)[["geometry"]].to_crs(CRS_PROJECTED_LIBYA)
    roads.geometry = roads.geometry.simplify(100, preserve_topology=True)
    road_layer = folium.FeatureGroup(name="Road network (embedded)")
    folium.GeoJson(
        roads.to_crs("EPSG:4326").to_json(),
        style_function=lambda _: {"color": "#c49553", "weight": 1.2, "opacity": 0.7},
        interactive=False,
    ).add_to(road_layer)
    road_layer.add_to(map_)

    settlements = folium.FeatureGroup(name="Settlement labels (embedded)")
    for _, place in gpd.read_file(POP_PLACES_GEOJSON_PATH).to_crs("EPSG:4326").iterrows():
        name = escape(str(place["featurename_en"]))
        folium.Marker(
            [place.geometry.y, place.geometry.x],
            icon=folium.DivIcon(
                html=f'<span class="settlement-label">{name}</span>',
                icon_size=(150, 16),
                icon_anchor=(-5, 8),
            ),
        ).add_to(settlements)
    settlements.add_to(map_)
    map_.get_root().header.add_child(
        folium.Element(
            """<style>
            .leaflet-container { background: #dcecf2 !important; }
            .settlement-label { font: 11px Arial, sans-serif; color: #334155;
                white-space: nowrap; text-shadow: 1px 1px white, -1px -1px white,
                1px -1px white, -1px 1px white; }
            </style>"""
        )
    )


def generate_interactive_map(
    recommendations_csv: Path = RECOMMENDATIONS_CSV,
    output_html: Path = RECOMMENDATIONS_MAP_HTML,
) -> Path:
    """Generate one map containing source evidence and proposed placements."""
    from antenna_cell_placement.data_cleaning import clean_pipeline

    _, sites = clean_pipeline()
    recommendations = (
        pd.read_csv(recommendations_csv) if recommendations_csv.exists() else pd.DataFrame()
    )

    map_ = folium.Map(location=[30.5, 17.5], zoom_start=6, tiles=None, control_scale=True)
    add_local_basemap(map_)
    _add_source_sites(map_, sites)
    _add_opencellid(map_)
    _add_collected_context(map_)
    _add_pilot_context(map_)
    _add_building_h3_context(map_, recommendations)
    _add_proposed_placements(map_, recommendations)
    folium.LayerControl(collapsed=False).add_to(map_)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    map_.save(output_html)
    rendered = output_html.read_text(encoding="utf-8")
    output_html.write_text(
        "\n".join(line.rstrip() for line in rendered.splitlines()) + "\n",
        encoding="utf-8",
    )
    print(f"Saved placement-review map to: {output_html}")
    return output_html


def _add_source_sites(map_: folium.Map, sites: pd.DataFrame) -> None:
    layers = {
        "multi": folium.FeatureGroup(name="Multi-technology source sites"),
        "LTE": folium.FeatureGroup(name="4G LTE source sites"),
        "UMTS": folium.FeatureGroup(name="3G UMTS source sites"),
        "GSM": folium.FeatureGroup(name="2G GSM source sites"),
    }
    colors = {"multi": "#2563eb", "LTE": "#16a34a", "UMTS": "#9333ea", "GSM": "#f59e0b"}
    for _, site in sites.iterrows():
        technologies = str(site["technologies"])
        category = "multi" if site["is_multi_tech"] else next(
            (rat for rat in ["LTE", "UMTS", "GSM"] if rat in technologies), "GSM"
        )
        bandwidth = (
            f"{site['total_bandwidth_mhz']} MHz"
            if pd.notna(site["total_bandwidth_mhz"])
            else "Not supplied"
        )
        popup = (
            f"<b>Source-derived physical site #{site['physical_site_id']}</b><br>"
            f"Technologies: {escape(technologies)}<br>"
            f"Operators: {escape(str(site['operators']))}<br>"
            f"Observed bandwidth: {bandwidth}<br>"
            f"Conflicting source locations: {bool(site['location_conflict'])}"
        )
        folium.CircleMarker(
            [site["canonical_latitude"], site["canonical_longitude"]],
            radius=4.5,
            color=colors[category],
            fill=True,
            fill_opacity=0.75,
            popup=folium.Popup(popup, max_width=300),
        ).add_to(layers[category])
    for layer in layers.values():
        layer.add_to(map_)


def _add_opencellid(map_: folium.Map) -> None:
    from antenna_cell_placement.opencellid import import_pipeline

    cells, _ = import_pipeline()
    for operator, subset in cells.groupby("operator"):
        layer = folium.FeatureGroup(name=f"OpenCellID estimates: {operator}", show=False)
        cluster = MarkerCluster().add_to(layer)
        for _, cell in subset.iterrows():
            popup = (
                f"<b>OpenCellID estimated cell - {escape(operator)}</b><br>"
                f"{escape(cell['radio'])}; area {cell['area']}; cell {cell['cell']}<br>"
                f"Measurements: {cell['samples']}<br>Last observed: {cell['updated_utc']}<br>"
                f"Estimated source range: {cell['range']} m<br>"
                "Not a verified mast or coverage footprint."
            )
            folium.Marker(
                [cell["lat"], cell["lon"]], popup=folium.Popup(popup, max_width=320)
            ).add_to(cluster)
        layer.add_to(map_)


def _add_proposed_placements(map_: folium.Map, recommendations: pd.DataFrame) -> None:
    if recommendations.empty:
        return
    layer = folium.FeatureGroup(name="Proposed placements")
    for _, proposal in recommendations.iterrows():
        review = (
            "Nearby recent OpenCellID observation; manual review required."
            if bool(proposal.get("opencellid_review_required", False))
            else "No nearby recent OpenCellID observation; coverage remains unverified."
        )
        landcover_review = (
            "Mixed/coastal land-cover context; manual review required."
            if bool(proposal.get("worldcover_review_required", False))
            else "WorldCover H3 context passed the automated screening checks."
        )
        building_context = (
            f"Mapped OSM buildings in H3 unit: {int(proposal['osm_building_count_h3']):,}"
            if pd.notna(proposal.get("osm_building_count_h3"))
            else "Mapped building context unavailable."
        )
        building_review = (
            "Mapped-building context conflicts with built-up evidence; manual review required."
            if bool(proposal.get("osm_building_review_required", False))
            else ""
        )
        osm_context = (
            "Selected OSM review context: "
            f"hospital {proposal['osm_hospital_nearest_distance_m'] / 1000.0:.1f} km; "
            f"higher education {proposal['osm_higher_education_nearest_distance_m'] / 1000.0:.1f} km; "
            f"aviation {proposal['osm_aviation_nearest_distance_m'] / 1000.0:.1f} km; "
            f"industrial land use {proposal['osm_industrial_nearest_distance_m'] / 1000.0:.1f} km."
            if bool(proposal.get("osm_selected_context_available", False))
            else "Selected OSM review context unavailable."
        )
        popup = (
            f"<b>Proposed placement #{proposal['recommendation_rank']}</b><br>"
            f"Municipality: {escape(str(proposal['municipality_name']))}<br>"
            f"H3 resolution 7: {escape(str(proposal.get('h3_r7', 'Unavailable')))}<br>"
            f"Planning priority: {proposal['planning_priority_score']:.2f}<br>"
            f"Reasons: {escape(str(proposal['reason_codes']))}<br>"
            f"5 km population: {int(proposal['population_sum_5km']):,}<br>"
            f"Known-site gap: {proposal['dist_to_nearest_site_m'] / 1000.0:.2f} km<br>"
            f"Point land cover: {escape(str(proposal.get('worldcover_class_name', 'Unavailable')))}<br>"
            f"H3 dominant land cover: {escape(str(proposal.get('worldcover_h3_dominant_class_name', 'Unavailable')))}<br>"
            f"{building_context}<br>{escape(building_review)}<br>"
            f"{escape(osm_context)}<br>"
            f"{review}<br>{landcover_review}"
        )
        folium.CircleMarker(
            [proposal["canonical_latitude"], proposal["canonical_longitude"]],
            radius=8,
            color="#b91c1c",
            weight=2.5,
            fill=True,
            fill_color="#ef4444",
            fill_opacity=0.9,
            popup=folium.Popup(popup, max_width=340),
        ).add_to(layer)
    layer.add_to(map_)


def _add_building_h3_context(
    map_: folium.Map,
    recommendations: pd.DataFrame,
) -> None:
    """Show mapped-building context for each shortlisted planning unit."""
    required = {"h3_r7", "osm_building_count_h3", "osm_building_coverage_ratio_h3"}
    if recommendations.empty or not required.issubset(recommendations.columns):
        return
    layer = folium.FeatureGroup(name="Mapped buildings by H3 unit", show=False)
    for _, row in recommendations.drop_duplicates("h3_r7").iterrows():
        if pd.isna(row["h3_r7"]) or pd.isna(row["osm_building_count_h3"]):
            continue
        count = int(row["osm_building_count_h3"])
        ratio = float(row["osm_building_coverage_ratio_h3"])
        color = "#0f766e" if count else "#a16207"
        coordinates = [
            [latitude, longitude]
            for latitude, longitude in h3.cell_to_boundary(str(row["h3_r7"]))
        ]
        folium.Polygon(
            locations=coordinates,
            color=color,
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.18,
            tooltip=(
                f"Mapped buildings: {count:,}; "
                f"footprint coverage: {100.0 * ratio:.2f}%"
            ),
        ).add_to(layer)
    layer.add_to(map_)




def _add_collected_context(map_: folium.Map) -> None:
    from antenna_cell_placement.collected_data import load_measurements, load_beacon

    measurements, _ = load_measurements()
    if not measurements.empty:
        layer = folium.FeatureGroup(name="Phone signal measurements (receiver locations)", show=False)
        cluster = MarkerCluster().add_to(layer)
        for _, row in measurements.iterrows():
            popup = (f"<b>Phone measurement — not an antenna location</b><br>"
                     f"{escape(str(row.net_type))}; MNC {int(row.mnc)}; cell {int(row.cell_id)}<br>"
                     f"Signal: {row.dbm} dBm; GPS accuracy: {row.accuracy} m<br>"
                     f"Measured: {row.measured_at}<br>Review eligible: {bool(row.review_eligible)}")
            folium.Marker([row.lat, row.lon], popup=folium.Popup(popup, max_width=340)).add_to(cluster)
        layer.add_to(map_)
    beacon, _ = load_beacon()
    if not beacon.empty:
        layer = folium.FeatureGroup(name="BeaconDB geolocation estimates", show=False)
        cluster = MarkerCluster().add_to(layer)
        for _, row in beacon.iterrows():
            popup = (f"<b>BeaconDB estimate — not a surveyed mast</b><br>"
                     f"{escape(str(row.radio_type))}; MNC {int(row.mnc)}; cell {int(row.cell_id)}<br>"
                     f"Reported accuracy: {row.beacondb_accuracy_m} m")
            folium.Marker([row.beacondb_lat, row.beacondb_lon], popup=folium.Popup(popup, max_width=340)).add_to(cluster)
        layer.add_to(map_)


def _add_pilot_context(map_: folium.Map) -> None:
    from antenna_cell_placement.config import REPORTS_DIR
    from antenna_cell_placement.pilot import _cell_geometry

    areas = REPORTS_DIR / 'measured_service_areas.geojson'
    report = REPORTS_DIR / 'pilot_review.json'
    if areas.exists():
        features = json.loads(areas.read_text())['features']
        pairs = sorted({(feature['properties']['mnc'], feature['properties']['net_type']) for feature in features})
        for mnc, radio in pairs:
            layer = folium.FeatureGroup(name=f"Measured service by operator and technology: MNC {int(mnc)} / {radio}", show=False)
            subset = {'type': 'FeatureCollection', 'features': [feature for feature in features
                      if feature['properties']['mnc'] == mnc and feature['properties']['net_type'] == radio]}
            folium.GeoJson(
                subset,
                style_function=lambda _: {"color": "#0891b2", "weight": 1, "fillOpacity": 0.18},
                tooltip=folium.GeoJsonTooltip(
                    fields=['mnc', 'net_type', 'sample_count', 'day_count', 'spatial_bins_r9', 'median_dbm', 'median_lte_rsrp_dbm'],
                    aliases=['MNC', 'Technology', 'Samples', 'Days', 'Spatial bins', 'Block median dBm', 'LTE RSRP dBm'],
                ),
            ).add_to(layer)
            layer.add_to(map_)
    if report.exists():
        data = json.loads(report.read_text())
        pilot = data['pilot']
        if 'h3_r7' in pilot:
            layer = folium.FeatureGroup(name="Measured pilot area (review only)", show=False)
            folium.GeoJson(_cell_geometry(pilot['h3_r7']),
                           style_function=lambda _: {"color": "#e11d48", "weight": 3, "fillOpacity": .05}).add_to(layer)
            folium.Marker([pilot['latitude'], pilot['longitude']], popup=folium.Popup(
                f"<b>Measured pilot — review only</b><br>Training samples: {pilot['training_samples']}<br>"
                f"Held-out samples: {pilot['holdout_samples']}<br>RF validation ready: False", max_width=320)).add_to(layer)
            layer.add_to(map_)
        conflicts = folium.FeatureGroup(name="Location conflicts requiring survey", show=False)
        for decision in data['reconciliation']['decisions']:
            for alternative in decision['alternatives']:
                label = (f"<b>Unresolved location</b><br>MNC {escape(str(decision['mnc']))}; "
                         f"{escape(decision['rat'])}; site {escape(str(decision['site_id']))}<br>"
                         f"Source verified: {alternative['source_verified']}<br>Last seen: {escape(str(alternative['last_seen_utc']))}<br>"
                         f"Decision: {escape(decision['status'])}<br>Independent survey required")
                folium.CircleMarker([alternative['latitude'], alternative['longitude']], radius=7,
                                    color='#dc2626', popup=folium.Popup(label, max_width=340)).add_to(conflicts)
        conflicts.add_to(map_)


if __name__ == "__main__":
    generate_interactive_map()
