from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "churn_datasets"
DEFAULT_DATASET_PATH = DATA_DIR / "Maven_telecom" / "telecom_customer_churn.csv"
MODEL_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "eval_reports"

# Target & Excluded columns
DROP_COLS = [
    "Customer ID", "Customer Status", "Churn Category", "Churn Reason",
    "City", "Zip Code", "Latitude", "Longitude"
]

TARGET_COL = "Churn"

CATEGORICAL_COLS = [
    "Gender", "Married", "Offer", "Phone Service", "Multiple Lines",
    "Internet Service", "Internet Type", "Online Security", "Online Backup",
    "Device Protection Plan", "Premium Tech Support", "Streaming TV",
    "Streaming Movies", "Streaming Music", "Unlimited Data", "Contract",
    "Paperless Billing", "Payment Method"
]

NUMERICAL_COLS = [
    "Age", "Number of Dependents", "Number of Referrals", "Tenure in Months",
    "Avg Monthly Long Distance Charges", "Avg Monthly GB Download",
    "Monthly Charge", "Total Charges", "Total Refunds", "Total Extra Data Charges",
    "Total Long Distance Charges", "Total Revenue"
]

# Business & Retention Discount Rules
DISCOUNT_TIERS = {
    "VIP_SAVE": {
        "min_prob": 0.50,
        "min_revenue": 3000.0,
        "discount_pct": 20,
        "target_offer": "Offer A (Annual VIP Lock-in)",
        "perk": "Free Premium Tech Support & Device Protection bundle + Unlimited Data",
        "priority": "Critical - High Value",
    },
    "STANDARD_SAVE": {
        "min_prob": 0.50,
        "min_revenue": 0.0,
        "discount_pct": 15,
        "target_offer": "Offer B (Standard Annual Retention)",
        "perk": "Free Online Security upgrade (6 months) + Waive extra data charges",
        "priority": "High - Moderate Value",
    },
    "PROACTIVE_SAVE": {
        "min_prob": 0.35,
        "min_revenue": 0.0,
        "discount_pct": 12,
        "target_offer": "Offer C (Contract Migration Guarantee)",
        "perk": "Annual rate lock guarantee + 10GB bonus bandwidth",
        "priority": "Medium - Early Warning",
    },
    "LOYALTY_COURTESY": {
        "min_prob": 0.20,
        "min_revenue": 0.0,
        "discount_pct": 5,
        "target_offer": "Account Checkup / Loyalty Credit",
        "perk": "One-time courtesy bill credit + service checkup",
        "priority": "Low - Courtesy Retention",
    },
    "NO_DISCOUNT": {
        "min_prob": 0.0,
        "min_revenue": 0.0,
        "discount_pct": 0,
        "target_offer": "Maintain Current Plan",
        "perk": "Standard Customer Care / Margin protected",
        "priority": "None - Organic Retention",
    }
}
