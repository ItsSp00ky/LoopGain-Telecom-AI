"""Command-line entry point. Each pipeline stage adds one subcommand here."""

import argparse
import datetime
import json
from pathlib import Path

from prepaid_churn.data import PROJECT_ROOT, RAW_TRAIN_PATH, REPORTS_DIR, load_raw

CONTRACT_PATH = PROJECT_ROOT / "docs" / "data_contract.md"
OUTPUT_CONTRACT_PATH = PROJECT_ROOT / "docs" / "output_contract.md"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "artifacts" / "models"
BUNDLE_DIR = PROJECT_ROOT / "artifacts" / "bundle"
SCORES_PATH = PROJECT_ROOT / "artifacts" / "scores" / "scores.csv"
VIEW_PATH = PROJECT_ROOT / "artifacts" / "scores" / "almadar_view.csv"
TIER_MODEL_PATH = PROJECT_ROOT / "artifacts" / "tiers" / "tiers.json"
TIERS_PATH = PROJECT_ROOT / "artifacts" / "scores" / "tiers.csv"
# Kaggle's unlabeled customers: never used for evaluation, so they stand in for "this month's base".
RAW_SCORE_PATH = PROJECT_ROOT / "data" / "raw" / "test.csv"
GATE_FILE = "gate.json"


def run_profile(args: argparse.Namespace) -> None:
    from prepaid_churn.profile import build_report

    report = build_report(load_raw(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Profile written to {args.output}")


def run_validate(args: argparse.Namespace) -> None:
    from prepaid_churn.schema import validate

    df = validate(load_raw(args.input))
    print(f"{args.input} matches the data contract ({len(df)} rows).")


def run_contract(args: argparse.Namespace) -> None:
    from prepaid_churn.schema import contract_markdown

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(contract_markdown(), encoding="utf-8")
    print(f"Data contract written to {args.output}")


def run_build_dataset(args: argparse.Namespace) -> None:
    from prepaid_churn.clean import clean
    from prepaid_churn.schema import validate
    from prepaid_churn.windows import build_datasets, dataset_report

    cleaned = clean(validate(load_raw(args.input)))
    datasets = build_datasets(cleaned, high_value_only=args.high_value)
    output_dir = args.output_dir / ("high_value" if args.high_value else "all")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in datasets.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    report = args.report or REPORTS_DIR / f"dataset_{output_dir.name}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(dataset_report(cleaned, datasets), encoding="utf-8")
    print(f"Datasets written to {output_dir}, summary in {report}")


def run_train(args: argparse.Namespace) -> None:
    import joblib
    import pandas as pd

    from prepaid_churn.training import train_models, training_report

    frames = {}
    for name in ("train", "validation"):
        path = args.data_dir / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run `uv run churn build-dataset` first.")
        frames[name] = pd.read_parquet(path)
    models = train_models(frames["train"])
    model_dir = MODELS_DIR / args.data_dir.name
    model_dir.mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        joblib.dump(model, model_dir / f"{name}.joblib")
    report = REPORTS_DIR / f"training_{args.data_dir.name}.md"
    report.write_text(training_report(models, frames["train"], frames["validation"]), "utf-8")
    print(f"Models written to {model_dir}, report in {report}")


def run_evaluate(args: argparse.Namespace) -> None:
    import joblib
    import pandas as pd

    from prepaid_churn.evaluation import evaluation_report, freeze, release_gate

    variant = args.data_dir.name
    model_dir = MODELS_DIR / variant
    models = {}
    for name in ("logistic_regression", "lightgbm"):
        path = model_dir / f"{name}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run `uv run churn train` first.")
        models[name] = joblib.load(path)
    validation = pd.read_parquet(args.data_dir / "validation.parquet")
    test = pd.read_parquet(args.data_dir / "test.parquet")

    champion, choices = freeze(models, validation, args.chosen_at)
    joblib.dump(champion, model_dir / "champion.joblib")
    gate = release_gate(champion, choices, models, test)
    (model_dir / GATE_FILE).write_text(json.dumps(gate, indent=2), encoding="utf-8")
    report = REPORTS_DIR / f"evaluation_{variant}.md"
    report.write_text(evaluation_report(champion, choices, models, test, gate), encoding="utf-8")
    print(f"Champion frozen in {model_dir / 'champion.joblib'}, report in {report}")
    print(f"Release gate {'passed' if gate['passed'] else 'FAILED'} ({model_dir / GATE_FILE})")


def run_bundle(args: argparse.Namespace) -> None:
    import joblib
    import pandas as pd

    from prepaid_churn.bundle import build_bundle, save_bundle

    model_dir = MODELS_DIR / args.data_dir.name
    champion_path, gate_path = model_dir / "champion.joblib", model_dir / GATE_FILE
    for path in (champion_path, gate_path):
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run `uv run churn evaluate` first.")
    gate = json.loads(gate_path.read_text("utf-8"))
    examples = pd.read_parquet(args.data_dir / "validation.parquet")
    created_at = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    bundle = build_bundle(joblib.load(champion_path), gate, examples, created_at)
    save_bundle(bundle, args.output_dir)
    print(f"Bundle {bundle.version} written to {args.output_dir}")


def run_score(args: argparse.Namespace) -> None:
    from prepaid_churn.bundle import load_bundle
    from prepaid_churn.scoring import score

    bundle = load_bundle(args.bundle)
    scores = score(load_raw(args.input), bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(args.output, index=False, encoding="utf-8")
    counts = scores["risk_band"].value_counts().to_dict()
    print(f"{len(scores)} subscribers scored with {bundle.version} into {args.output}: {counts}")


def run_almadar_view(args: argparse.Namespace) -> None:
    from prepaid_churn.almadar import almadar_view, load_market, load_offers, view_report
    from prepaid_churn.clean import clean
    from prepaid_churn.schema import validate
    from prepaid_churn.scoring import SCORING_WINDOW
    from prepaid_churn.windows import active_in_current_month

    market = load_market()
    cleaned = clean(validate(load_raw(args.input), labeled=False))
    view = almadar_view(cleaned, SCORING_WINDOW, market, load_offers())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    view.to_csv(args.output, index=False, encoding="utf-8")
    active = active_in_current_month(cleaned, SCORING_WINDOW)
    report = view_report(view, active, market, args.input.name)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(f"Almadar view of {len(view)} customers in {args.output}, summary in {args.report}")


def run_fit_tiers(args: argparse.Namespace) -> None:
    import pandas as pd

    from prepaid_churn.almadar import load_market
    from prepaid_churn.segmentation import compare_clusters, tiers_report, write_cluster_plots
    from prepaid_churn.value import apply_tiers, fit_tiers, save_tiers

    train = pd.read_parquet(args.train)
    model = fit_tiers(train, load_market())
    comparison = compare_clusters(apply_tiers(train, model))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_cluster_plots(comparison, args.report.parent)
    args.report.write_text(tiers_report(train, model, comparison), encoding="utf-8")
    save_tiers(model, args.output)
    print(f"Tier artifact {model.version} in {args.output}, comparison in {args.report}")


def run_tiers(args: argparse.Namespace) -> None:
    from prepaid_churn.bundle import load_bundle
    from prepaid_churn.value import load_tiers, tier_export

    model = load_tiers(args.model)
    bundle = None if args.tiers_only else load_bundle(args.bundle)
    result = tier_export(load_raw(args.input), model, bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8")
    counts = result["value_tier"].value_counts().to_dict()
    print(f"{len(result)} subscribers assigned tiers with {model.version}: {counts}")
    print(f"Output: {args.output}; value status: {result['value_status'].value_counts().to_dict()}")


def run_output_contract(args: argparse.Namespace) -> None:
    from prepaid_churn.scoring import output_contract_markdown

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_contract_markdown(), encoding="utf-8")
    print(f"Output contract written to {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="churn",
        description="Churn risk model for prepaid telecom subscribers.",
    )
    commands = parser.add_subparsers(dest="command", title="commands")

    profile = commands.add_parser("profile", help="Profile the raw data (ticket T1).")
    profile.add_argument("--input", type=Path, default=RAW_TRAIN_PATH)
    profile.add_argument("--output", type=Path, default=REPORTS_DIR / "profile.md")
    profile.set_defaults(handler=run_profile)

    validate = commands.add_parser(
        "validate", help="Check an export against the data contract (ticket T2)."
    )
    validate.add_argument("--input", type=Path, default=RAW_TRAIN_PATH)
    validate.set_defaults(handler=run_validate)

    contract = commands.add_parser("contract", help="Write the data contract document (ticket T2).")
    contract.add_argument("--output", type=Path, default=CONTRACT_PATH)
    contract.set_defaults(handler=run_contract)

    build = commands.add_parser(
        "build-dataset", help="Build train, validation and test windows (ticket T4)."
    )
    build.add_argument("--input", type=Path, default=RAW_TRAIN_PATH)
    build.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    build.add_argument("--report", type=Path, default=None)
    build.add_argument(
        "--high-value", action="store_true", help="Keep only the top 30%% by recharge amount."
    )
    build.set_defaults(handler=run_build_dataset)

    train = commands.add_parser("train", help="Train the baseline and LightGBM (ticket T6).")
    train.add_argument("--data-dir", type=Path, default=PROCESSED_DIR / "all")
    train.set_defaults(handler=run_train)

    evaluate = commands.add_parser(
        "evaluate", help="Calibrate, freeze choices, then score the test window once (ticket T7)."
    )
    evaluate.add_argument("--data-dir", type=Path, default=PROCESSED_DIR / "all")
    evaluate.add_argument(
        "--chosen-at",
        default=datetime.date.today().isoformat(),
        help="Date recorded as the freeze date (default: today).",
    )
    evaluate.set_defaults(handler=run_evaluate)

    bundle = commands.add_parser(
        "bundle", help="Package the champion that passed its release gate (ticket T8)."
    )
    bundle.add_argument("--data-dir", type=Path, default=PROCESSED_DIR / "all")
    bundle.add_argument("--output-dir", type=Path, default=BUNDLE_DIR)
    bundle.set_defaults(handler=run_bundle)

    score = commands.add_parser(
        "score", help="Score every subscriber of an export into the output contract (ticket T8)."
    )
    score.add_argument("--input", type=Path, default=RAW_SCORE_PATH)
    score.add_argument("--output", type=Path, default=SCORES_PATH)
    score.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    score.set_defaults(handler=run_score)

    view = commands.add_parser(
        "almadar-view", help="Show every customer in Almadar money and packages (ticket T18)."
    )
    view.add_argument("--input", type=Path, default=RAW_SCORE_PATH)
    view.add_argument("--output", type=Path, default=VIEW_PATH)
    view.add_argument("--report", type=Path, default=REPORTS_DIR / "almadar_view.md")
    view.set_defaults(handler=run_almadar_view)

    fit_tiers = commands.add_parser(
        "fit-tiers", help="Freeze value cutoffs on training window A and compare clusters (T10)."
    )
    fit_tiers.add_argument("--train", type=Path, default=PROCESSED_DIR / "all" / "train.parquet")
    fit_tiers.add_argument("--output", type=Path, default=TIER_MODEL_PATH)
    fit_tiers.add_argument("--report", type=Path, default=REPORTS_DIR / "tiers.md")
    fit_tiers.set_defaults(handler=run_fit_tiers)

    tiers = commands.add_parser(
        "tiers", help="Add frozen value tiers and 12-month scenarios (T10)."
    )
    tiers.add_argument("--input", type=Path, default=RAW_SCORE_PATH)
    tiers.add_argument("--model", type=Path, default=TIER_MODEL_PATH)
    tiers.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    tiers.add_argument("--output", type=Path, default=TIERS_PATH)
    tiers.add_argument(
        "--tiers-only",
        action="store_true",
        help="Do not load a churn bundle; leave value scenarios empty and label risk unavailable.",
    )
    tiers.set_defaults(handler=run_tiers)

    output_contract = commands.add_parser(
        "output-contract", help="Write the subscriber output contract document (ticket T8)."
    )
    output_contract.add_argument("--output", type=Path, default=OUTPUT_CONTRACT_PATH)
    output_contract.set_defaults(handler=run_output_contract)

    return parser


def main(argv: list[str] | None = None) -> None:
    from prepaid_churn.almadar import InvalidCatalogueError
    from prepaid_churn.bundle import BundleError
    from prepaid_churn.schema import InvalidExportError
    from prepaid_churn.value import ValueModelError

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return
    try:
        args.handler(args)
    except (
        FileNotFoundError,
        InvalidExportError,
        BundleError,
        InvalidCatalogueError,
        ValueModelError,
    ) as error:
        parser.exit(1, f"error: {error}\n")
