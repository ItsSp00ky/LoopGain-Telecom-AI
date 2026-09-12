from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "churn_datasets"
DEFAULT_DATASET_PATH = DATA_DIR / "Telco_customer_churn.xlsx" / "Telco_customer_churn.xlsx"
MODEL_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "eval_reports"

# Feature definitions
DROP_COLS = [
    "CustomerID", "Count", "Country", "State", "City", "Zip Code",
    "Lat Long", "Latitude", "Longitude", "Churn Label", "Churn Score",
    "Churn Reason"
]

TARGET_COL = "Churn Value"

CATEGORICAL_COLS = [
    "Gender", "Senior Citizen", "Partner", "Dependents", "Phone Service",
    "Multiple Lines", "Internet Service", "Online Security", "Online Backup",
    "Device Protection", "Tech Support", "Streaming TV", "Streaming Movies",
    "Contract", "Paperless Billing", "Payment Method"
]

NUMERICAL_COLS = [
    "Tenure Months", "Monthly Charges", "Total Charges", "CLTV"
]

# Business & Retention Discount Rules
DISCOUNT_TIERS = {
    "VIP_SAVE": {
        "min_prob": 0.50,
        "min_cltv": 4200,
        "discount_pct": 20,
        "contract_term": "1-Year Agreement Required",
        "perk": "Free Tech Support + Device Protection bundle (12 months)",
        "priority": "Critical - High Value",
    },
    "STANDARD_SAVE": {
        "min_prob": 0.50,
        "min_cltv": 0,
        "discount_pct": 15,
        "contract_term": "1-Year Agreement Required",
        "perk": "Free Online Security upgrade (6 months)",
        "priority": "High - Moderate Value",
    },
    "PROACTIVE_SAVE": {
        "min_prob": 0.35,
        "min_cltv": 0,
        "discount_pct": 10,
        "contract_term": "Convert to 1-Year Price Guarantee",
        "perk": "Annual loyalty rate lock",
        "priority": "Medium - Early Warning",
    },
    "NO_DISCOUNT": {
        "min_prob": 0.0,
        "min_cltv": 0,
        "discount_pct": 0,
        "contract_term": "Maintain Current Plan",
        "perk": "Standard Customer Care / No discount needed",
        "priority": "Low - Low Churn Risk",
    }
}
