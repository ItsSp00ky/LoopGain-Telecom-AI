from typing import Dict, Any, List
import pandas as pd
import numpy as np

class TelecomDiscountEngine:
    """
    Business Rules and Optimization Engine for targeted telecom customer retention.
    Determines discount eligibility, package recommendations, and expected ROI.
    """

    def __init__(self, acceptance_rate: float = 0.70):
        self.acceptance_rate = acceptance_rate

    def evaluate_customer(
        self,
        churn_prob: float,
        monthly_charges: float,
        cltv: float,
        contract: str,
        internet_service: str,
        has_tech_support: bool = False,
        has_security: bool = False,
        tenure_months: int = 12
    ) -> Dict[str, Any]:
        """
        Determines targeted retention action for a single customer.
        """
        # Tier Decision Logic
        if churn_prob >= 0.60:
            if cltv >= 4000 or monthly_charges >= 75.0:
                tier = "VIP_SAVE"
                discount_pct = 20
                action = "Aggressive VIP Retention Plan"
                contract_offer = "1-Year or 2-Year Contract Commitment"
                package_add_on = "Free Tech Support & Device Protection bundle (12 months)"
                urgency = "Critical"
            else:
                tier = "STANDARD_SAVE"
                discount_pct = 15
                action = "Standard Retention Offer"
                contract_offer = "1-Year Contract Commitment"
                package_add_on = "Free Online Security upgrade (6 months)"
                urgency = "High"
        elif churn_prob >= 0.40:
            if contract == "Month-to-month":
                tier = "PROACTIVE_SAVE"
                discount_pct = 12
                action = "Contract Migration Incentive"
                contract_offer = "Switch to 1-Year Plan with Fixed-Rate Guarantee"
                package_add_on = "Complimentary speed boost or streaming add-on (3 months)"
                urgency = "Medium"
            else:
                tier = "LOYALTY_COURTESY"
                discount_pct = 5
                action = "Loyalty Account Checkup"
                contract_offer = "Maintain existing contract with bill courtesy credit"
                package_add_on = "Account health review & feature optimization"
                urgency = "Low"
        else:
            tier = "NO_DISCOUNT"
            discount_pct = 0
            action = "Organic Retention / No Discount"
            contract_offer = "Maintain Current Terms"
            package_add_on = "Standard customer communications"
            urgency = "None"

        # Financial modeling
        annual_spend = monthly_charges * 12
        annual_discount_cost = annual_spend * (discount_pct / 100.0)
        new_monthly_charge = monthly_charges * (1 - discount_pct / 100.0)

        # Expected revenue saved factoring churn probability and acceptance rate
        expected_saved_revenue = annual_spend * churn_prob * self.acceptance_rate
        net_retention_gain = expected_saved_revenue - annual_discount_cost if discount_pct > 0 else 0.0
        roi_pct = (net_retention_gain / annual_discount_cost * 100.0) if annual_discount_cost > 0 else 0.0

        # Specific package tailored advice
        package_notes = []
        if internet_service == "Fiber optic" and not has_tech_support:
            package_notes.append("Customer on Fiber Optic without Tech Support - prime risk for technical dissatisfaction. Include proactive onboarding/support.")
        if contract == "Month-to-month":
            package_notes.append("Customer on Month-to-Month. Strong candidate for 12-month lock-in agreement.")
        if tenure_months <= 6:
            package_notes.append("Early tenure customer (first 6 months) - high vulnerability window.")

        return {
            "churn_probability": round(float(churn_prob), 4),
            "risk_level": "High" if churn_prob >= 0.6 else ("Medium" if churn_prob >= 0.4 else "Low"),
            "retention_tier": tier,
            "urgency": urgency,
            "recommended_action": action,
            "discount_percentage": discount_pct,
            "current_monthly_charge": round(float(monthly_charges), 2),
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
            mc = row.get("Monthly Charges", 65.0)
            cltv = row.get("CLTV", 4000.0)
            contract = row.get("Contract", "Month-to-month")
            internet = row.get("Internet Service", "Fiber optic")
            ts = row.get("Tech Support", "No") == "Yes"
            sec = row.get("Online Security", "No") == "Yes"
            tenure = row.get("Tenure Months", 12)

            rec = self.evaluate_customer(
                churn_prob=prob,
                monthly_charges=mc,
                cltv=cltv,
                contract=contract,
                internet_service=internet,
                has_tech_support=ts,
                has_security=sec,
                tenure_months=tenure
            )
            rec["CustomerID"] = row.get("CustomerID", f"CUST-{idx}")
            results.append(rec)

        res_df = pd.DataFrame(results)
        # Reorder columns
        front_cols = ["CustomerID", "churn_probability", "risk_level", "retention_tier", "discount_percentage", "current_monthly_charge", "new_monthly_charge", "contract_recommendation"]
        other_cols = [c for c in res_df.columns if c not in front_cols]
        return res_df[front_cols + other_cols]

if __name__ == "__main__":
    engine = TelecomDiscountEngine()
    sample = engine.evaluate_customer(
        churn_prob=0.72,
        monthly_charges=89.50,
        cltv=5100,
        contract="Month-to-month",
        internet_service="Fiber optic",
        has_tech_support=False,
        has_security=False,
        tenure_months=4
    )
    for k, v in sample.items():
        print(f"{k}: {v}")
