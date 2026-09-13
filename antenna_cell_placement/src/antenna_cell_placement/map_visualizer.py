"""
Interactive Leaflet/Folium geospatial visualization for Libyan cell sites and AI placement recommendations.
"""

from pathlib import Path
import folium
from folium.plugins import MarkerCluster, FeatureGroupSubGroup
import pandas as pd

from antenna_cell_placement.config import (
    CLEANED_PHYSICAL_SITES_CSV,
    RECOMMENDATIONS_CSV,
    CLEANED_MAP_HTML,
    REPORTS_DIR,
)


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

    # Center map on Libya
    center_lat = 30.5
    center_lon = 17.5
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
        control_scale=True
    )

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
            <p style="margin: 2px 0;"><b>Total Bandwidth:</b> {bw} MHz</p>
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

    # 2. Feature Group for AI Placement Recommendations
    if df_recs is not None and not df_recs.empty:
        fg_recs = folium.FeatureGroup(name="⭐ AI Recommended Placements (Top 50)")

        for _, row in df_recs.iterrows():
            lat = row["canonical_latitude"]
            lon = row["canonical_longitude"]
            rank = row["recommendation_rank"]
            muni = row["municipality_name"]
            place = row["nearest_settlement_name"]
            score = row["placement_suitability_score"]
            tier = row["recommended_equipment_tier"]
            bands = row["recommended_rf_bands"]
            pop_5k = row["population_sum_5km"]
            gap_m = row["dist_to_nearest_site_m"]
            p_score = row["deployment_priority_score"]

            rec_popup = f"""
            <div style="font-family: Arial, sans-serif; min-width: 250px;">
                <div style="background: #dc2626; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;">
                    ⭐ AI Recommended Placement Rank #{rank}
                </div>
                <p style="margin: 6px 0 3px;"><b>Municipality:</b> {muni} ({place})</p>
                <p style="margin: 3px 0;"><b>Suitability Score:</b> <span style="color: #16a34a; font-weight: bold;">{score:.4f}</span></p>
                <p style="margin: 3px 0;"><b>Priority Score:</b> {p_score}</p>
                <p style="margin: 3px 0;"><b>Equipment Tier:</b> {tier}</p>
                <p style="margin: 3px 0;"><b>Recommended Bands:</b> {bands}</p>
                <p style="margin: 3px 0;"><b>5km Population Served:</b> {int(pop_5k):,} people</p>
                <p style="margin: 3px 0;"><b>Nearest Tower Gap:</b> {gap_m / 1000.0:.2f} km</p>
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


if __name__ == "__main__":
    generate_interactive_map()
