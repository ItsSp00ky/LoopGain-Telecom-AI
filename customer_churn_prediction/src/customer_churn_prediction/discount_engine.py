from typing import Dict, Any, List
import pandas as pd
import numpy as np

class TelecomDiscountEngine:
    """
    Retention & Discount Recommendation Engine tailored for the Maven Telecom dataset.
    Prescribes targeted marketing offers (Offer A/B/C), contract lock-ins,
    unlimited data bundles, and ROI calculations.
    """

    def __init__(self, acceptance_rate: float = 0.75):
        self.acceptance_rate = acceptance_rate

    def evaluate_customer(
        self,
        churn_prob: float,
        monthly_charge: float,
        total_revenue: float,
        current_offer: str,
        contract: str,
        internet_type: str,
        avg_gb_download: float = 20.0,
        extra_data_charges: float = 0.0,
        refunds: float = 0.0,
        has_tech_support: bool = False,
        has_security: bool = False,
        tenure_months: int = 12
    ) -> Dict[str, Any]:
        """
        Prescribes personalized retention offers for a single customer.
        """
        package_notes = []

        # Tier Decision Logic
        if churn_prob >= 0.60:
            if total_revenue >= 2500.0 or monthly_charge >= 75.0:
                tier = "VIP_SAVE"
                discount_pct = 20
                action = "VIP Retention Plan (Migrate to Offer A)"
                target_offer = "Offer A (Annual Fixed-Rate VIP)"
                contract_offer = "1-Year or 2-Year Contract Commitment"
                package_add_on = "Complimentary Premium Tech Support & Device Protection + Unlimited Data (12m)"
                urgency = "Critical"
            else:
                tier = "STANDARD_SAVE"
                discount_pct = 15
                action = "Standard Retention Plan (Migrate to Offer B)"
                target_offer = "Offer B (Standard Annual Saver)"
                contract_offer = "1-Year Contract Commitment"
                package_add_on = "Free Online Security upgrade (6m) + Unlimited Data trial"
                urgency = "High"
        elif churn_prob >= 0.35:
            if contract == "Month-to-Month":
                tier = "PROACTIVE_SAVE"
                discount_pct = 12
                action = "Annual Contract Migration (Offer C)"
                target_offer = "Offer C (Contract Price Lock)"
                contract_offer = "Switch from Month-to-Month to 1-Year Rate Guarantee"
                package_add_on = "10 GB bonus bandwidth or streaming credit"
                urgency = "Medium"
            else:
                tier = "LOYALTY_COURTESY"
                discount_pct = 5
                action = "Loyalty Appreciation Credit"
                target_offer = "Offer D (Loyalty Courtesy)"
                contract_offer = "Maintain Current Terms with monthly courtesy credit"
                package_add_on = "Service checkup & network performance review"
                urgency = "Low"
        else:
            tier = "NO_DISCOUNT"
            discount_pct = 0
            action = "Organic Retention / Margin Protected"
            target_offer = "Maintain Current Plan"
            contract_offer = "Maintain Current Terms"
            package_add_on = "Standard customer care"
            urgency = "None"

        # Strategic Telecom Diagnostics
        if current_offer == "Offer E":
            package_notes.append("URGENT: Customer is on Offer E (67.6% historical churn rate). Immediate migration to Offer A or B required.")

        if extra_data_charges > 0:
            package_notes.append(f"Bill Shock: Customer accrued ${extra_data_charges:.2f} in extra data fees. Waive fees and upgrade to Unlimited Data.")

        if refunds > 0:
            package_notes.append(f"Service Friction: Customer received ${refunds:.2f} in refunds. Proactive outreach recommended to resolve technical issues.")

        if internet_type == "Fiber Optic" and not has_tech_support:
            package_notes.append("Fiber Optic account without Premium Tech Support. High risk of switching providers over support friction.")

        if avg_gb_download >= 50:
            package_notes.append(f"Heavy Data User ({avg_gb_download:.1f} GB/mo). Bundle Unlimited Data to prevent overage churn.")
        elif avg_gb_download < 10 and internet_type != "No internet service":
            package_notes.append(f"Low Data User ({avg_gb_download:.1f} GB/mo). Offer optimized lower-tier broadband to reduce bill pressure.")

        # Financial modeling
        annual_spend = monthly_charge * 12
        annual_discount_cost = annual_spend * (discount_pct / 100.0)
        new_monthly_charge = monthly_charge * (1 - discount_pct / 100.0)

        # Expected saved revenue
        expected_saved_revenue = annual_spend * churn_prob * self.acceptance_rate
        net_retention_gain = expected_saved_revenue - annual_discount_cost if discount_pct > 0 else 0.0
        roi_pct = (net_retention_gain / annual_discount_cost * 100.0) if annual_discount_cost > 0 else 0.0

        return {
            "churn_probability": round(float(churn_prob), 4),
            "risk_level": "High" if churn_prob >= 0.6 else ("Medium" if churn_prob >= 0.35 else "Low"),
            "retention_tier": tier,
            "urgency": urgency,
            "recommended_action": action,
            "prescribed_offer": target_offer,
            "discount_percentage": discount_pct,
            "current_monthly_charge": round(float(monthly_charge), 2),
            "new_monthly_charge": round(float(new_monthly_charge), 2),
            "contract_recommendation": contract_offer,
            "package_add_ons": package_add_on,
            "expected_annual_discount_cost": round(float(annual_discount_cost), 2),
            "expected_saved_revenue": round(float(expected_saved_revenue), 2),
            "net_retention_gain": round(float(net_retention_gain), 2),
            "roi_percentage": round(float(roi_pct), 1),
            "strategic_notes": package_notes
        }

    def batch_recommend(
        self,
        df: pd.DataFrame,
        churn_probs: np.ndarray
    ) -> pd.DataFrame:
        """
        Runs recommendation logic across a dataframe of customers.
        """
        results = []
        for i, (idx, row) in enumerate(df.iterrows()):
            prob = churn_probs[i]
            mc = row.get("Monthly Charge", 65.0)
            rev = row.get("Total Revenue", row.get("Total Charges", 3000.0))
            offer = str(row.get("Offer", "None"))
            contract = str(row.get("Contract", "Month-to-Month"))
            internet = str(row.get("Internet Type", "Fiber Optic"))
            gb = float(row.get("Avg Monthly GB Download", 20.0))
            extra_fees = float(row.get("Total Extra Data Charges", 0.0))
            refunds = float(row.get("Total Refunds", 0.0))
            ts = (row.get("Premium Tech Support", "No") == "Yes")
            sec = (row.get("Online Security", "No") == "Yes")
            tenure = int(row.get("Tenure in Months", 12))

            rec = self.evaluate_customer(
                churn_prob=prob,
                monthly_charge=mc,
                total_revenue=rev,
                current_offer=offer,
                contract=contract,
                internet_type=internet,
                avg_gb_download=gb,
                extra_data_charges=extra_fees,
                refunds=refunds,
                has_tech_support=ts,
                has_security=sec,
                tenure_months=tenure
            )
            rec["CustomerID"] = row.get("Customer ID", f"CUST-{idx}")
            results.append(rec)

        res_df = pd.DataFrame(results)
        front_cols = [
            "CustomerID", "churn_probability", "risk_level", "retention_tier",
            "prescribed_offer", "discount_percentage", "current_monthly_charge",
            "new_monthly_charge", "contract_recommendation"
        ]
        other_cols = [c for c in res_df.columns if c not in front_cols]
        return res_df[front_cols + other_cols]

if __name__ == "__main__":
    engine = TelecomDiscountEngine()
    sample = engine.evaluate_customer(
        churn_prob=0.88,
        monthly_charge=85.50,
        total_revenue=3400.0,
        current_offer="Offer E",
        contract="Month-to-Month",
        internet_type="Fiber Optic",
        avg_gb_download=65.0,
        extra_data_charges=30.0,
        refunds=25.0,
        has_tech_support=False,
        has_security=False,
        tenure_months=5
    )
    for k, v in sample.items():
        print(f"{k}: {v}")
