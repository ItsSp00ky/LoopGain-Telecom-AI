"""
src/config.py
Single Source of Truth for 3GPP Rel-17 KPI Specifications, SLA Thresholds,
Physical Domain Boundaries, Spectrum Definitions, and NOC Color Palettes.
"""

from typing import Dict, Any, List, Tuple
import numpy as np

# 3GPP Functional Taxonomy Categories
KPI_CATEGORIES = {
    'Accessibility': ['rrc_setup_sr', 'erab_estab_sr'],
    'Retainability': ['erab_drop_rate'],
    'Mobility': ['handover_sr', 'handover_intra_sr'],
    'Capacity & Traffic': ['dl_throughput_mbps', 'ul_throughput_mbps', 'connected_users'],
    'Availability & Survivability': ['availability_pct', 'downtime_sec']
}

# 3GPP Rel-17 Standardized Key Performance Indicators
KPI_CONFIG: Dict[str, Dict[str, Any]] = {
    'rrc_setup_sr': {
        'name': 'RRC Setup Success Rate',
        'unit': '%',
        'category': 'Accessibility',
        'desc': 'Radio Resource Control connection establishment success rate',
        'format': '{:.2f}%',
        'domain': '[0.0, 100.0%]',
        'min_val': 0.0,
        'max_val': 100.0,
        'transform': 'identity',
        'sla_target': 99.0,
        'sla_op': '>=',
        'sla_desc': 'Target: >= 99.00%'
    },
    'erab_estab_sr': {
        'name': 'E-RAB Establishment Rate',
        'unit': '%',
        'category': 'Accessibility',
        'desc': 'E-UTRAN Radio Access Bearer initialization success percentage',
        'format': '{:.2f}%',
        'domain': '[0.0, 100.0%]',
        'min_val': 0.0,
        'max_val': 100.0,
        'transform': 'identity',
        'sla_target': 99.0,
        'sla_op': '>=',
        'sla_desc': 'Target: >= 99.00%'
    },
    'erab_drop_rate': {
        'name': 'E-RAB Drop Rate',
        'unit': '%',
        'category': 'Retainability',
        'desc': 'Abnormal bearer session termination percentage',
        'format': '{:.3f}%',
        'domain': '[0.0, 100.0%]',
        'min_val': 0.0,
        'max_val': 100.0,
        'transform': 'identity',
        'sla_target': 0.5,
        'sla_op': '<=',
        'sla_desc': 'Target: <= 0.500%'
    },
    'handover_intra_sr': {
        'name': 'Intra-Freq Handover Success',
        'unit': 'ratio',
        'category': 'Mobility',
        'desc': 'Intra-frequency sector transition execution accuracy',
        'format': '{:.4f}',
        'domain': '[0.0, 1.0]',
        'min_val': 0.0,
        'max_val': 1.0,
        'transform': 'identity',
        'sla_target': 0.98,
        'sla_op': '>=',
        'sla_desc': 'Target: >= 0.9800'
    },
    'handover_sr': {
        'name': 'Overall Handover Success Rate',
        'unit': '%',
        'category': 'Mobility',
        'desc': 'Aggregated inter/intra-carrier handover execution rate',
        'format': '{:.2f}%',
        'domain': '[0.0, 100.0%]',
        'min_val': 0.0,
        'max_val': 100.0,
        'transform': 'identity',
        'sla_target': 98.0,
        'sla_op': '>=',
        'sla_desc': 'Target: >= 98.00%'
    },
    'availability_pct': {
        'name': 'Cell Operational Availability',
        'unit': '%',
        'category': 'Availability & Survivability',
        'desc': 'Cell radio uptime ratio over scheduled operational hours',
        'format': '{:.2f}%',
        'domain': '[0.0, 100.0%]',
        'min_val': 0.0,
        'max_val': 100.0,
        'transform': 'identity',
        'sla_target': 99.5,
        'sla_op': '>=',
        'sla_desc': 'Target: >= 99.50%'
    },
    'dl_throughput_mbps': {
        'name': 'Downlink User Throughput',
        'unit': 'Mbps',
        'category': 'Capacity & Traffic',
        'desc': 'Mean downlink data throughput per subscriber session',
        'format': '{:.2f} Mbps',
        'domain': '>= 0.0 Mbps',
        'min_val': 0.0,
        'max_val': None,
        'transform': 'log1p',
        'sla_target': 5.0,
        'sla_op': '>=',
        'sla_desc': 'Nominal: >= 5.00 Mbps'
    },
    'ul_throughput_mbps': {
        'name': 'Uplink User Throughput',
        'unit': 'Mbps',
        'category': 'Capacity & Traffic',
        'desc': 'Mean uplink data throughput per subscriber session',
        'format': '{:.2f} Mbps',
        'domain': '>= 0.0 Mbps',
        'min_val': 0.0,
        'max_val': None,
        'transform': 'log1p',
        'sla_target': 1.0,
        'sla_op': '>=',
        'sla_desc': 'Nominal: >= 1.00 Mbps'
    },
    'connected_users': {
        'name': 'Active Connected Users',
        'unit': 'UEs',
        'category': 'Capacity & Traffic',
        'desc': 'Simultaneously active user equipment (UE) instances',
        'format': '{:.1f}',
        'domain': '>= 0 UEs',
        'min_val': 0.0,
        'max_val': None,
        'transform': 'log1p',
        'sla_target': 1.0,
        'sla_op': '>=',
        'sla_desc': 'Traffic active'
    },
    'downtime_sec': {
        'name': 'Cluster Cell Downtime',
        'unit': 'cell-sec',
        'category': 'Availability & Survivability',
        'desc': 'Cluster-aggregated cell outage duration (cumulative cell-seconds across regional sector tier)',
        'format': '{:,.0f}s',
        'domain': '>= 0 sec',
        'min_val': 0.0,
        'max_val': None,
        'transform': 'log1p',
        'sla_target': 3600.0,
        'sla_op': '<=',
        'sla_desc': 'Nominal: <= 3,600 cell-sec / sector'
    }
}

KPI_KEYS: List[str] = list(KPI_CONFIG.keys())

# Carrier Frequency Spectrum Definitions & Regional Cluster Sizing
CARRIER_BANDS: List[int] = [350, 400, 1556, 1700, 3500, 6200]

CARRIER_BAND_NAMES: Dict[int, str] = {
    350: "Band 350 MHz (Macro Coverage Tier ~667 Cells)",
    400: "Band 400 MHz (Rural Sub-1GHz Cluster ~9 Cells)",
    1556: "Band 1556 MHz (Mid-Band FDD Urban ~83 Cells)",
    1700: "Band 1700 MHz (AWS/PCS Uplink Tier ~27 Cells)",
    3500: "Band 3500 MHz (C-Band Regional Capacity ~253 Cells)",
    6200: "Band 6200 MHz (High-Throughput Small Cell / Micro ~28 Cells)"
}

CARRIER_CLUSTER_CELLS: Dict[int, int] = {
    350: 667,
    400: 9,
    1556: 83,
    1700: 27,
    3500: 253,
    6200: 28
}

BAND_COLORS: Dict[int, str] = {
    350: '#10B981',   # Emerald Green
    400: '#3B82F6',   # Blue
    1556: '#F59E0B',  # Amber
    1700: '#EC4899',  # Pink
    3500: '#8B5CF6',  # Purple
    6200: '#06B6D4'   # Cyan
}

# 3GPP Physical Domain Constants
SECONDS_PER_DAY: float = 86400.0
DAYS_PER_YEAR: float = 365.25
DEFAULT_SPLIT_RATIOS: Dict[str, float] = {'train': 0.70, 'val': 0.15, 'test': 0.15}
DEFAULT_FORECAST_HORIZON_DAYS: int = 365

# Prefix classification rules mapping raw cell base station identifiers into 3GPP spectrum frequency tiers
ERBS_CARRIER_PREFIX_RULES: List[Tuple[Tuple[str, ...], int]] = [
    (('NT',), 350),                                            # Band 350 MHz (Macro Regional Coverage Tier)
    (('SUR', 'TLILM', 'COW', 'VIP', 'TS', 'SBR'), 400),       # Band 400 MHz (Rural Sub-1GHz Cluster)
    (('NSB', 'NSU'), 1556),                                   # Band 1556 MHz (Mid-Band FDD Urban Tier)
    (('ZWY', 'ZW', 'PH'), 1700),                              # Band 1700 MHz (AWS/PCS Uplink Tier)
    (('NZW', 'ZAW', 'TR', 'T', 'TI'), 3500),                  # Band 3500 MHz (C-Band Regional Capacity Tier)
]
DEFAULT_CARRIER_BAND: int = 6200                              # Band 6200 MHz (High-Throughput Small Cell / Micro Cluster)

# Mapping of raw vendor telemetry columns to 3GPP standardized KPI keys
RAW_COLUMN_TO_KPI_MAP: Dict[str, str] = {
    'RRC Setup Success Rate': 'rrc_setup_sr',
    'E-RAB Establishment Success Rate': 'erab_estab_sr',
    'E-RAB Drop Rate': 'erab_drop_rate',
    'Handover Success Rate ( 4G Intra System)': 'handover_intra_sr',
    'Handover Success Rate': 'handover_sr',
    '4G Cell Av. (%)': 'availability_pct',
    'E-UTRAN IP Throughput UE DL': 'dl_throughput_mbps',
    'E-UTRAN IP Throughput UE UL': 'ul_throughput_mbps',
    'Avg RRC Connected users': 'connected_users',
    'pmCellDowntimeMan': 'downtime_sec',
    'downtime_sec': 'downtime_sec',
}

def apply_bounds(arr: np.ndarray, kpi: str) -> np.ndarray:
    """
    Enforces strict physical domain limits and 3GPP specifications on predictions.
    Prevents mathematical divergence, negative rates, and >100% probabilities.
    """
    arr = np.asarray(arr, dtype=float)
    meta = KPI_CONFIG.get(kpi, {})
    min_v = meta.get('min_val', 0.0)
    max_v = meta.get('max_val', None)
    return np.clip(arr, min_v, max_v)

def check_sla_compliance(value: float, kpi: str) -> bool:
    """Evaluates whether a metric value satisfies the operational SLA target."""
    meta = KPI_CONFIG.get(kpi, {})
    target = meta.get('sla_target')
    op = meta.get('sla_op')
    if target is None or op is None:
        return True
    if op == '>=':
        return value >= target
    elif op == '<=':
        return value <= target
    return True
