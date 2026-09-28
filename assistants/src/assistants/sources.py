"""Every file the copilot reads from the teammates' folders, in one place (decision 55).

These are committed outputs and data of the GIS and network ML modules. Their owners keep
the paths stable; if one moves, only this module changes. The copilot never writes to them.
"""

from pathlib import Path

REPO = Path(__file__).parents[3]

# Maher's network_kpi_prediction: one row per base station per day, and the network totals.
TOWER_KPIS = REPO / "network_kpi_prediction" / "data" / "erbs_cell_kpi_full_year.csv"
NETWORK_KPIS = REPO / "network_kpi_prediction" / "data" / "macro_network_kpis_daily.csv"
TRAFFIC_VOLUME = REPO / "network_kpi_prediction" / "data" / "4g_traffic_volume_daily.csv"

# Mahmoud and Ahmed's integrated GIS release: the ranked sites and every candidate.
GIS_RELEASE = REPO / "antenna_cell_placement" / "integrated_release"
SHORTLIST = GIS_RELEASE / "shortlist.csv"
CANDIDATES = GIS_RELEASE / "candidates.csv"
MANIFEST = GIS_RELEASE / "manifest.json"

# Where confirmed work orders go: this project's own runtime folder, git-ignored.
WORK_ORDERS = Path(__file__).parents[2] / "runtime" / "work_orders.jsonl"
