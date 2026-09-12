import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

class TelecomFeatureEngineer(BaseEstimator, TransformerMixin):
    """
    Custom scikit-learn transformer that computes telecom domain features
    for churn risk and discount decisioning.
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
            ("Online Security", "Yes"),
            ("Online Backup", "Yes"),
            ("Device Protection", "Yes"),
            ("Tech Support", "Yes"),
            ("Streaming TV", "Yes"),
            ("Streaming Movies", "Yes"),
        ]
        total_services = pd.Series(0, index=X_out.index)
        for col, target_val in service_cols:
            if col in X_out.columns:
                total_services += (X_out[col] == target_val).astype(int)

        if "Internet Service" in X_out.columns:
            total_services += (X_out["Internet Service"].isin(["DSL", "Fiber optic"])).astype(int)

        X_out["TotalServicesCount"] = total_services

        # 2. Bundles & convenience features
        if "Online Security" in X_out.columns and "Tech Support" in X_out.columns:
            X_out["HasSecurityBundle"] = (
                (X_out["Online Security"] == "Yes") & (X_out["Tech Support"] == "Yes")
            ).astype(int)

        if "Streaming TV" in X_out.columns and "Streaming Movies" in X_out.columns:
            X_out["HasStreamingBundle"] = (
                (X_out["Streaming TV"] == "Yes") & (X_out["Streaming Movies"] == "Yes")
            ).astype(int)

        if "Payment Method" in X_out.columns:
            X_out["IsAutoPay"] = (
                X_out["Payment Method"].astype(str).str.contains("automatic", case=False)
            ).astype(int)

        if "Contract" in X_out.columns:
            X_out["IsMonthToMonth"] = (X_out["Contract"] == "Month-to-month").astype(int)

        if "Partner" in X_out.columns and "Dependents" in X_out.columns:
            X_out["HasFamily"] = (
                (X_out["Partner"] == "Yes") | (X_out["Dependents"] == "Yes")
            ).astype(int)

        # 3. Financial ratios
        if "Monthly Charges" in X_out.columns:
            X_out["MonthlyChargesPerService"] = X_out["Monthly Charges"] / (total_services + 1)

        if "Total Charges" in X_out.columns and "Tenure Months" in X_out.columns and "Monthly Charges" in X_out.columns:
            expected_total = X_out["Tenure Months"] * X_out["Monthly Charges"]
            X_out["ChargesRatio"] = np.where(
                expected_total > 0,
                X_out["Total Charges"] / (expected_total + 1e-5),
                1.0
            )

        # 4. Tenure Cohort
        if "Tenure Months" in X_out.columns:
            X_out["TenureCohort"] = pd.cut(
                X_out["Tenure Months"],
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
