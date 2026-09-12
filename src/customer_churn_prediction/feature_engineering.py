import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

class TelecomFeatureEngineer(BaseEstimator, TransformerMixin):
    """
    Custom scikit-learn transformer that computes telecom domain features
    for the Maven Telecom dataset to maximize churn prediction and discount targeting.
    """
    def __init__(self):
        pass

    def fit(self, X, y=None):
        return self

    def transform(self, X, y=None):
        X_out = X.copy()

        # 1. Total service count
        service_cols = [
            ("Phone Service", "Yes"),
            ("Multiple Lines", "Yes"),
            ("Internet Service", "Yes"),
            ("Online Security", "Yes"),
            ("Online Backup", "Yes"),
            ("Device Protection Plan", "Yes"),
            ("Premium Tech Support", "Yes"),
            ("Streaming TV", "Yes"),
            ("Streaming Movies", "Yes"),
            ("Streaming Music", "Yes"),
            ("Unlimited Data", "Yes"),
        ]
        total_services = pd.Series(0, index=X_out.index)
        for col, target_val in service_cols:
            if col in X_out.columns:
                total_services += (X_out[col] == target_val).astype(int)

        X_out["TotalServicesCount"] = total_services

        # 2. Bundles & convenience features
        if "Online Security" in X_out.columns and "Premium Tech Support" in X_out.columns:
            X_out["HasSecurityBundle"] = (
                (X_out["Online Security"] == "Yes") & (X_out["Premium Tech Support"] == "Yes")
            ).astype(int)

        if "Streaming TV" in X_out.columns and "Streaming Movies" in X_out.columns:
            streaming_series = (X_out["Streaming TV"] == "Yes") & (X_out["Streaming Movies"] == "Yes")
            if "Streaming Music" in X_out.columns:
                streaming_series = streaming_series & (X_out["Streaming Music"] == "Yes")
            X_out["HasStreamingBundle"] = streaming_series.astype(int)

        if "Payment Method" in X_out.columns:
            X_out["IsAutoPay"] = (
                X_out["Payment Method"].astype(str).str.contains("Bank|Credit Card", case=False)
            ).astype(int)

        if "Contract" in X_out.columns:
            X_out["IsMonthToMonth"] = (X_out["Contract"] == "Month-to-Month").astype(int)

        # 3. Bill Shock & Outage friction
        if "Total Extra Data Charges" in X_out.columns:
            X_out["HasExtraDataCharges"] = (X_out["Total Extra Data Charges"] > 0).astype(int)
            if "Total Charges" in X_out.columns:
                X_out["ExtraDataChargeRatio"] = (
                    X_out["Total Extra Data Charges"] / (X_out["Total Charges"] + 1e-5)
                )

        if "Total Refunds" in X_out.columns:
            X_out["HasRefunds"] = (X_out["Total Refunds"] > 0).astype(int)
            if "Total Revenue" in X_out.columns:
                X_out["RefundRatio"] = (
                    X_out["Total Refunds"] / (X_out["Total Revenue"] + 1e-5)
                )

        # 4. Loyalty & Usage signals
        if "Number of Referrals" in X_out.columns:
            X_out["HasReferrals"] = (X_out["Number of Referrals"] > 0).astype(int)

        if "Avg Monthly GB Download" in X_out.columns:
            X_out["IsHeavyDataUser"] = (X_out["Avg Monthly GB Download"] >= 50).astype(int)

        # 5. Offer Risk Categorization
        if "Offer" in X_out.columns:
            X_out["IsOfferE"] = (X_out["Offer"] == "Offer E").astype(int)
            X_out["IsOfferAorB"] = (X_out["Offer"].isin(["Offer A", "Offer B"])).astype(int)

        # 6. Financial efficiency
        if "Monthly Charge" in X_out.columns:
            X_out["MonthlyChargesPerService"] = X_out["Monthly Charge"] / (total_services + 1)

        # 7. Tenure Cohort
        if "Tenure in Months" in X_out.columns:
            X_out["TenureCohort"] = pd.cut(
                X_out["Tenure in Months"],
                bins=[-1, 12, 24, 48, 100],
                labels=["0-12m", "13-24m", "25-48m", "49m+"]
            ).astype(str)

        return X_out

if __name__ == "__main__":
    from customer_churn_prediction.data_loader import load_and_clean_data
    X, y, meta = load_and_clean_data()
    fe = TelecomFeatureEngineer()
    X_trans = fe.fit_transform(X)
    print("Transformed columns:", X_trans.columns.tolist())
    print("New shape:", X_trans.shape)
