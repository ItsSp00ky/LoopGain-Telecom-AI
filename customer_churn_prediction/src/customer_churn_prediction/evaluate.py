import os
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import (
    roc_curve, roc_auc_score, precision_recall_curve,
    average_precision_score, confusion_matrix, classification_report
)

from customer_churn_prediction.config import MODEL_DIR, REPORTS_DIR

def run_comprehensive_evaluation():
    """
    Evaluates the champion model on test predictions and generates visual plots.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    test_preds_path = REPORTS_DIR / "test_predictions.csv"
    model_path = MODEL_DIR / "best_churn_model.joblib"

    if not test_preds_path.exists() or not model_path.exists():
        raise FileNotFoundError("Model or test predictions not found. Run model_trainer first.")

    df_test = pd.read_csv(test_preds_path)
    y_true = df_test["y_true"].values
    y_probs = df_test["churn_prob"].values

    pipeline = joblib.load(model_path)
    preprocessor = pipeline.named_steps["preprocessor"]
    classifier = pipeline.named_steps["classifier"]

    # 1. Optimal Threshold Analysis (F1 and Business Cost Curve)
    thresholds = np.linspace(0.1, 0.9, 81)
    f1_scores = []
    for t in thresholds:
        preds = (y_probs >= t).astype(int)
        tp = np.sum((y_true == 1) & (preds == 1))
        fp = np.sum((y_true == 0) & (preds == 1))
        fn = np.sum((y_true == 1) & (preds == 0))
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0
        f1_scores.append(f1)

    best_idx = np.argmax(f1_scores)
    best_thresh = thresholds[best_idx]
    best_f1 = f1_scores[best_idx]

    print(f"Optimal F1 Decision Threshold: {best_thresh:.2f} (F1 Score: {best_f1:.4f})")

    y_preds_opt = (y_probs >= best_thresh).astype(int)
    cm = confusion_matrix(y_true, y_preds_opt)
    report_dict = classification_report(y_true, y_preds_opt, output_dict=True)

    # 2. Plot Confusion Matrix
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False,
                xticklabels=["Stay (0)", "Churn (1)"],
                yticklabels=["Stay (0)", "Churn (1)"])
    plt.title(f"Confusion Matrix (Threshold = {best_thresh:.2f})")
    plt.xlabel("Predicted Label")
    plt.ylabel("Actual Label")
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "confusion_matrix.png", dpi=300)
    plt.close()

    # 3. Plot ROC Curve
    fpr, tpr, _ = roc_curve(y_true, y_probs)
    auc_score = roc_auc_score(y_true, y_probs)

    plt.figure(figsize=(7, 6))
    plt.plot(fpr, tpr, color="#2563EB", lw=2.5, label=f"Champion XGBoost (AUC = {auc_score:.4f})")
    plt.plot([0, 1], [0, 1], color="gray", lw=1.5, linestyle="--", label="Random Chance")
    plt.xlabel("False Positive Rate (1 - Specificity)")
    plt.ylabel("True Positive Rate (Recall)")
    plt.title("Receiver Operating Characteristic (ROC) Curve")
    plt.legend(loc="lower right")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "roc_curve.png", dpi=300)
    plt.close()

    # 4. Plot Precision-Recall Curve
    precision_vals, recall_vals, _ = precision_recall_curve(y_true, y_probs)
    pr_auc = average_precision_score(y_true, y_probs)

    plt.figure(figsize=(7, 6))
    plt.plot(recall_vals, precision_vals, color="#059669", lw=2.5, label=f"Champion XGBoost (PR-AUC = {pr_auc:.4f})")
    baseline_churn_rate = float(np.mean(y_true))
    plt.axhline(baseline_churn_rate, color="gray", lw=1.5, linestyle="--", label=f"Baseline Churn Rate ({baseline_churn_rate:.1%})")
    plt.xlabel("Recall (Coverage of Churners)")
    plt.ylabel("Precision (Accuracy of Churn Alerts)")
    plt.title("Precision-Recall Curve")
    plt.legend(loc="upper right")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "precision_recall_curve.png", dpi=300)
    plt.close()

    # 5. Plot Probability Distribution by Churn Status
    plt.figure(figsize=(8, 5))
    sns.kdeplot(y_probs[y_true == 0], label="Retained Customers (Stay)", color="#3B82F6", fill=True, alpha=0.4)
    sns.kdeplot(y_probs[y_true == 1], label="Churned Customers (Leave)", color="#EF4444", fill=True, alpha=0.4)
    plt.axvline(best_thresh, color="black", linestyle="--", label=f"Decision Threshold ({best_thresh:.2f})")
    plt.xlabel("Predicted Churn Probability")
    plt.ylabel("Density")
    plt.title("Distribution of Predicted Churn Probabilities")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "probability_distribution.png", dpi=300)
    plt.close()

    # 6. Feature Importance Bar Chart
    if hasattr(classifier, "feature_importances_"):
        feature_names = preprocessor.get_feature_names_out()
        importances = classifier.feature_importances_
        fi_df = pd.DataFrame({
            "Feature": [f.replace("cat__", "").replace("num__", "") for f in feature_names],
            "Importance": importances
        }).sort_values(by="Importance", ascending=False).head(15)

        plt.figure(figsize=(10, 6))
        sns.barplot(data=fi_df, x="Importance", y="Feature", hue="Feature", legend=False, palette="viridis")
        plt.title("Top 15 Most Predictive Features (Telecom Churn)")
        plt.xlabel("Relative Importance")
        plt.ylabel("Feature")
        plt.tight_layout()
        plt.savefig(REPORTS_DIR / "feature_importance.png", dpi=300)
        plt.close()

    print(f"Evaluation plots saved to: {REPORTS_DIR}")
    return {
        "best_threshold": float(best_thresh),
        "best_f1": float(best_f1),
        "roc_auc": float(auc_score),
        "pr_auc": float(pr_auc),
        "classification_report": report_dict
    }

if __name__ == "__main__":
    res = run_comprehensive_evaluation()
