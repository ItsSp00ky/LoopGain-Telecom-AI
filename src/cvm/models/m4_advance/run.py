"""Entry point: `python -m cvm.models.m4_advance.run`  (phase 7)

Trains the two PD heads, quantifies the selection bias, corrects for it, and
scores the base through the full limit function with every safety guard applied.

    1. build the label            observed only for subscribers who borrowed
    2. quantify the bias          the observed population is not a random sample
    3. correct it                 fuzzy augmentation over the never-borrowed
    4. train both PD heads        calibrated, because the bands are absolute
    5. score the whole base       limit = min(four terms), then the guards

STEP 2 COMES BEFORE STEP 3 ON PURPOSE. The textbook direction of selection
bias in credit is that the observed population is the safer tail, so the
correction pulls the estimate down. Almadar's gate is `balance <= 0.5 LYD`,
which selects on being BROKE -- so the direction is not the textbook one and
cannot be assumed. Measuring it first is the difference between applying a
correction and performing one.
"""

from __future__ import annotations

import argparse
import json
import logging

import joblib
import numpy as np
import pandas as pd

from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct
from cvm.config import load_conf, settings
from cvm.decision import advance_limit
from cvm.models.m4_advance import reject_inference, repayment_pd

log = logging.getLogger(__name__)


def load_base() -> pd.DataFrame:
    """The population with CLV joined -- h(CLV) is one of the four terms."""
    features = settings.feature_store_offline
    population = settings.synthetic_dir / "population.parquet"
    for path in (features, population):
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist; run the earlier phases first")

    frame = pd.read_parquet(features)
    latest = (
        frame.sort_values("snapshot_date")
        .drop_duplicates(subset=["subscriber_id_hashed"], keep="last")
        .reset_index(drop=True)
    )

    # `days_to_settle` is a label artefact and is correctly absent from the
    # feature store. It is the OUTCOME here, so it comes from the population --
    # the same distinction M1b needed for `days_to_churn`.
    outcome = pd.read_parquet(population)[
        [
            "subscriber_id_hashed",
            "days_to_settle",
            "airtime_advance_count_90d",
            "data_advance_count_90d",
        ]
    ]
    merged = latest.merge(
        outcome, on="subscriber_id_hashed", how="inner", validate="1:1", suffixes=("", "_pop")
    )

    clv_path = settings.processed_dir / "m2_clv.parquet"
    if clv_path.exists():
        merged["clv_12m"] = pd.read_parquet(clv_path)["clv_12m"].to_numpy()
    else:
        log.warning("m2_clv.parquet absent; h(CLV) will not bind")
        merged["clv_12m"] = np.nan

    log.info("base: %d subscribers", len(merged))
    return merged


def _matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """The shared M1 feature matrix, with the advance OUTCOME columns removed.

    `days_to_settle` is the label. Leaving it in a PD feature matrix would let
    the model read the answer, which is the same class of mistake the leakage
    suite exists for -- met here in a module that issues credit.
    """
    from cvm.models.m1_churn.gradient_boosting import prepare_matrix

    drop = [
        c for c in ("days_to_settle", "repaid_by_next_recharge", "clv_12m") if c in frame.columns
    ]
    drop += [c for c in frame.columns if c.endswith("_pop")]
    X, _ = prepare_matrix(frame.drop(columns=drop))
    return X


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the PD heads and score advance limits.")
    parser.add_argument("--sample", type=int, default=0, help="score only N subscribers")
    args = parser.parse_args()

    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")
    settings.ensure_dirs()
    reports, artefacts = settings.reports_dir, settings.models_dir

    base = load_base()
    X_all = _matrix(base)

    results: dict[str, dict] = {}
    models: dict[str, object] = {}

    for product in repayment_pd.PRODUCTS:
        observed = repayment_pd.build_label(base, product)
        if len(observed) < 200:
            log.warning("only %d observed %s outcomes; skipping that head", len(observed), product)
            continue

        accepted = X_all.loc[observed.index].assign(
            repaid_by_next_recharge=observed["repaid_by_next_recharge"].to_numpy()
        )
        never_borrowed = X_all.drop(index=observed.index)

        # --- 2. Measure the bias BEFORE correcting it ------------------------
        bias = reject_inference.quantify_bias(accepted, never_borrowed)

        # --- 3 and 4. Correct, then fit -------------------------------------
        # A calibration slice is carved off the OBSERVED rows first and kept out
        # of both the naive fit and the augmentation. It is the only data with a
        # real outcome, and it is the only thing a calibrator may see -- fuzzy
        # labels are the model's own predictions wearing a label's clothes.
        from sklearn.model_selection import train_test_split

        fit_rows, cal_rows = train_test_split(
            accepted,
            test_size=0.3,
            random_state=settings.random_seed,
            stratify=accepted["repaid_by_next_recharge"],
        )
        calibration = (
            cal_rows.drop(columns=["repaid_by_next_recharge"]),
            cal_rows["repaid_by_next_recharge"],
        )

        naive = repayment_pd.train(
            fit_rows.drop(columns=["repaid_by_next_recharge"]),
            fit_rows["repaid_by_next_recharge"],
            product=product,
            calibration=calibration,
        )
        augmented = reject_inference.fuzzy_augmentation(fit_rows, never_borrowed, naive)

        corrected = repayment_pd.train(
            augmented.drop(columns=["repaid_by_next_recharge", reject_inference.WEIGHT]),
            augmented["repaid_by_next_recharge"],
            product=product,
            sample_weight=augmented[reject_inference.WEIGHT].to_numpy(),
            calibration=calibration,
        )
        models[product] = corrected

        naive_pd = repayment_pd.predict_pd(naive, X_all)
        corrected_pd = repayment_pd.predict_pd(corrected, X_all)
        results[product] = {
            "observed_outcomes": len(observed),
            "observed_repayment_rate": float(observed["repaid_by_next_recharge"].mean()),
            "selection_bias": bias,
            "mean_pd_naive": float(naive_pd.mean()),
            "mean_pd_corrected": float(corrected_pd.mean()),
            "correction_shift": float(corrected_pd.mean() - naive_pd.mean()),
        }

    if not models:
        raise RuntimeError("no PD head could be trained; the label has too few observations")

    # --- 5. Score the base through the full limit function -------------------
    scored = base if args.sample <= 0 else base.head(args.sample)
    X = X_all.loc[scored.index]

    airtime_pd = repayment_pd.predict_pd(models["airtime"], X)
    lockout = repayment_pd.predict_lockout_risk(models["airtime"], X, pd.Series(5.0, index=X.index))

    decisions = []
    for position, (_index, row) in enumerate(scored.iterrows()):
        features = {
            "repayment_probability": float(airtime_pd.iloc[position]),
            "lockout_risk": float(lockout.iloc[position]),
            "modal_recharge_amount_lyd": row.get("modal_recharge_amount_lyd", np.nan),
            "loyalty_tier": _tier(row.get("segment")),
            "clv_12m": row.get("clv_12m", np.nan),
            "balance_zero_hours_30d": row.get("balance_zero_hours_30d", 0.0),
            "failed_bundle_attempts_30d": row.get("failed_bundle_attempts_30d", 0.0),
            "consecutive_sub_5_lyd_recharges": row.get("consecutive_sub_5_lyd_recharges", 0.0),
            "emergency_service_alternations_90d": row.get(
                "emergency_service_alternations_90d", 0.0
            ),
            "airtime_advance_count_90d": row.get("airtime_advance_count_90d", 0.0),
            "data_advance_count_90d": row.get("data_advance_count_90d", 0.0),
            "days_since_last_advance": 30.0,
            "advances_this_month": 0.0,
            "cumulative_exposure_this_month_lyd": 0.0,
        }
        for product, enum in (("airtime", AdvanceProduct.AIRTIME), ("data", AdvanceProduct.DATA)):
            response = advance_limit.decide_limit(
                AdvanceLimitRequest(subscriber_id=str(row["subscriber_id_hashed"]), product=enum),
                features,
            )
            decisions.append(
                {
                    "subscriber_id_hashed": str(row["subscriber_id_hashed"]),
                    "product": product,
                    "approved": response.approved,
                    "limit_lyd": response.limit_lyd,
                    "repayment_probability": response.repayment_probability,
                    "lockout_risk": response.lockout_risk,
                    "lockout_flagged": response.lockout_flagged,
                    "binding_constraint": response.binding_constraint,
                    "modal_recharge_lyd": response.modal_recharge_lyd,
                    "fallback_offer_id": response.fallback_offer_id,
                }
            )

    table = pd.DataFrame(decisions)
    table.to_parquet(settings.processed_dir / "m4_advance.parquet")

    summary = {
        "subscribers_scored": len(scored),
        "pd_heads": results,
        "by_product": {
            product: {
                "approved": int(part["approved"].sum()),
                "approval_rate": float(part["approved"].mean()),
                "mean_limit_when_approved": (
                    float(part.loc[part["approved"], "limit_lyd"].mean())
                    if part["approved"].any()
                    else 0.0
                ),
                "binding_constraints": part.loc[~part["approved"], "binding_constraint"]
                .value_counts()
                .to_dict(),
                "lockout_flagged": int(part["lockout_flagged"].sum()),
            }
            for product, part in table.groupby("product")
        },
        "zero_residual_population": int(
            (
                scored["modal_recharge_amount_lyd"]
                <= load_conf("advance")["incumbent_critique"]["smallest_card_lyd"]
            ).sum()
        ),
    }
    (reports / "m4_advance.json").write_text(json.dumps(summary, indent=2, default=str))
    joblib.dump(models, artefacts / "m4_advance.joblib")

    # --- Report ---------------------------------------------------------------
    print(f"\n{'PD HEADS':<38}{'observed':>11}{'repay rate':>13}{'bias shift':>13}")
    print("-" * 76)
    for product, r in results.items():
        print(
            f"{product:<38}{r['observed_outcomes']:>11,}{r['observed_repayment_rate']:>13.4f}"
            f"{r['correction_shift']:>+13.4f}"
        )
        bias = r["selection_bias"]
        print(
            f"{'  worst covariate imbalance':<38}{bias['max_abs_smd_feature']:>11}"
            f"{bias['max_abs_smd']:>13.3f}{bias['features_above_0_25']:>13} above 0.25"
        )

    print(f"\n{'DECISIONS':<38}{'approved':>11}{'rate':>13}{'mean limit':>13}")
    print("-" * 76)
    for product, s in summary["by_product"].items():
        print(
            f"{product:<38}{s['approved']:>11,}{s['approval_rate']:>13.1%}"
            f"{s['mean_limit_when_approved']:>12.2f} LYD"
        )
        for reason, count in list(s["binding_constraints"].items())[:3]:
            print(f"{'  declined by ' + reason:<38}{count:>11,}")

    print(f"\n{'at the 5 LYD recharge floor':<38}{summary['zero_residual_population']:>11,}")
    print("\nNext: the decision engine -- see docs/ROADMAP.md#phase-8")


def _tier(segment) -> str:
    """Map an RFM-LE segment onto a loyalty tier.

    A placeholder mapping until M2's tiering lands in the decision engine, and
    it is stated rather than hidden: the tier ceiling is one of four terms and
    is rarely the binding one, so a rough mapping here does not change many
    decisions -- but it would be wrong to present it as the real tiering.
    """
    high = {"Champions", "Loyal High-Value"}
    mid = {"At-Risk Valuable", "Potential Loyalists", "Needs Attention"}
    if segment in high:
        return "gold"
    if segment in mid:
        return "silver"
    return "bronze"


if __name__ == "__main__":
    main()
