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
CAMPAIGN_DIR = PROJECT_ROOT / "artifacts" / "campaigns" / "retention"
ADVICE_PATH = PROJECT_ROOT / "artifacts" / "scores" / "advance.csv"
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


def run_decide(args: argparse.Namespace) -> None:
    from dataclasses import replace

    from prepaid_churn.almadar import load_offers
    from prepaid_churn.bundle import load_bundle
    from prepaid_churn.campaign import build_campaign, save_campaign
    from prepaid_churn.retention import decision_inputs, load_policy, propose
    from prepaid_churn.retention_report import decisions_report
    from prepaid_churn.value import load_tiers

    offers, policy = load_offers(), load_policy(args.policy)
    if args.budget is not None:
        policy = replace(policy, budget_lyd=args.budget)
    model = load_tiers(args.model)
    bundle = None if args.tiers_only else load_bundle(args.bundle)
    inputs = decision_inputs(load_raw(args.input), model, bundle, offers)
    decisions, comparison = propose(inputs, offers, policy)
    campaign = build_campaign(inputs, decisions, comparison, offers, policy)
    path = save_campaign(campaign, args.output_dir)
    report = decisions_report(decisions, comparison, offers, policy)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(f"{decisions['status'].eq('proposed').sum()} proposals in {path}; none are approved.")
    print(f"Decision report: {args.report}")


def run_approve(args: argparse.Namespace) -> None:
    from prepaid_churn.campaign import released_campaign, review_file
    from prepaid_churn.retention import RetentionError

    if args.refresh and (args.subscriber_id or args.reject or args.note):
        raise RetentionError("--refresh cannot be combined with review actions or a note.")
    reviewed = review_file(
        args.proposals,
        args.reviewer,
        "rejected" if args.reject else "approved",
        [] if args.refresh else args.subscriber_id,
        args.note,
    )
    print(
        f"{len(reviewed['reviews'])} reviews logged; "
        f"{len(released_campaign(reviewed))} approved rows in "
        f"{args.proposals.parent / 'released.csv'}"
    )


def run_advance(args: argparse.Namespace) -> None:
    from prepaid_churn.advance import advice_report, advise
    from prepaid_churn.almadar import load_market
    from prepaid_churn.clean import clean
    from prepaid_churn.schema import validate
    from prepaid_churn.scoring import SCORING_WINDOW

    market = load_market()
    cleaned = clean(validate(load_raw(args.input), labeled=False))
    advice = advise(cleaned, SCORING_WINDOW, market)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    advice.to_csv(args.output, index=False, encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(advice_report(advice, market, args.input.name), encoding="utf-8")
    counts = advice["advice_code"].value_counts().to_dict()
    print(f"Advice for {len(advice)} customers in {args.output}, report in {args.report}: {counts}")


def run_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from prepaid_churn.api import build_app
    from prepaid_churn.service import ServicePaths

    paths = ServicePaths(
        bundle_dir=args.bundle,
        portfolio_path=args.portfolio,
        campaign_path=args.campaign_dir / "proposals.json",
    )
    app = build_app(paths)
    print(f"Serving {args.host}:{args.port}; the OpenAPI page is at /docs.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def run_sequence_benchmark(args: argparse.Namespace) -> None:
    import joblib
    import pandas as pd

    from prepaid_churn.sequence import MODEL_NAME, benchmark, benchmark_report

    datasets = {}
    for name in ("train", "validation", "test"):
        path = args.data_dir / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run `uv run churn build-dataset` first.")
        datasets[name] = pd.read_parquet(path)
    model_dir = MODELS_DIR / args.data_dir.name
    gate_path = model_dir / GATE_FILE
    if not gate_path.exists():
        raise FileNotFoundError(f"{gate_path} not found. Run `uv run churn evaluate` first.")
    gate = json.loads(gate_path.read_text("utf-8"))
    baseline_path = model_dir / "logistic_regression.joblib"
    result = benchmark(
        datasets, gate, joblib.load(baseline_path) if baseline_path.exists() else None, args.seed
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(benchmark_report(result, gate, datasets), encoding="utf-8")
    champion = gate.get("champion", "the champion")
    champion_pr_auc = gate.get("test_metrics", {}).get(champion, {}).get("pr_auc")
    print(
        f"{MODEL_NAME} test PR-AUC {result['test_metrics']['pr_auc']:.4f} against {champion} "
        f"{champion_pr_auc:.4f}; report in {args.report}"
    )


def run_check_integration(args: argparse.Namespace) -> None:
    import os

    from prepaid_churn.api import CHATBOT_KEY_VARIABLE, COPILOT_KEY_VARIABLE
    from prepaid_churn.client import check
    from prepaid_churn.service import ServiceConfigurationError

    keys = {name: os.environ.get(name, "") for name in (CHATBOT_KEY_VARIABLE, COPILOT_KEY_VARIABLE)}
    missing = [name for name, key in keys.items() if not key]
    if missing:
        raise ServiceConfigurationError(
            f"Set {' and '.join(missing)} to the keys the service was started with. "
            "The check calls each endpoint with both keys, so it needs both."
        )
    result = check(
        args.url,
        keys[CHATBOT_KEY_VARIABLE],
        keys[COPILOT_KEY_VARIABLE],
        args.subscriber_id,
    )
    print(result.text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.text + "\n", encoding="utf-8")
        print(f"Written to {args.output}")
    if result.failures:
        raise SystemExit(1)


def run_output_contract(args: argparse.Namespace) -> None:
    from prepaid_churn.scoring import output_contract_markdown

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_contract_markdown(), encoding="utf-8")
    print(f"Output contract written to {args.output}")


def build_parser() -> argparse.ArgumentParser:
    from prepaid_churn.retention import POLICY_PATH

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

    decide = commands.add_parser(
        "decide", help="Propose budgeted retention bonuses for review (T11)."
    )
    decide.add_argument("--input", type=Path, default=RAW_SCORE_PATH)
    decide.add_argument("--model", type=Path, default=TIER_MODEL_PATH)
    decide.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    decide.add_argument("--policy", type=Path, default=POLICY_PATH)
    decide.add_argument(
        "--budget", type=float, default=None, help="Override campaign budget in LYD."
    )
    decide.add_argument("--output-dir", type=Path, default=CAMPAIGN_DIR)
    decide.add_argument("--report", type=Path, default=REPORTS_DIR / "decisions.md")
    decide.add_argument(
        "--tiers-only",
        action="store_true",
        help="Readiness run without churn risk; proposes no offers.",
    )
    decide.set_defaults(handler=run_decide)

    approve = commands.add_parser(
        "approve", help="Record a named review and release approvals (T11)."
    )
    approve.add_argument("--proposals", type=Path, required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument(
        "--subscriber-id",
        action="append",
        default=None,
        help="Review this pending subscriber; repeat, or omit for all pending.",
    )
    approve.add_argument("--reject", action="store_true", help="Reject instead of approving.")
    approve.add_argument("--note", default="")
    approve.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild release and log views without reviewing any pending rows.",
    )
    approve.set_defaults(handler=run_approve)

    output_contract = commands.add_parser(
        "output-contract", help="Write the subscriber output contract document (ticket T8)."
    )
    output_contract.add_argument("--output", type=Path, default=OUTPUT_CONTRACT_PATH)
    output_contract.set_defaults(handler=run_output_contract)

    advance = commands.add_parser(
        "advance",
        help="Advise an emergency credit limit per customer (ticket T19).",
        description=(
            "Rule-based advice only. It grants nothing, and a limit reaches a customer "
            "only after a person approves it (decision 14)."
        ),
    )
    advance.add_argument("--input", type=Path, default=RAW_SCORE_PATH)
    advance.add_argument("--output", type=Path, default=ADVICE_PATH)
    advance.add_argument("--report", type=Path, default=REPORTS_DIR / "emergency_credit.md")
    advance.set_defaults(handler=run_advance)

    serve = commands.add_parser(
        "serve",
        help="Serve the released outputs to the chatbot and the copilot (ticket T15).",
        description=(
            "Read-only HTTP service. Set PREPAID_CHURN_CHATBOT_KEY and "
            "PREPAID_CHURN_COPILOT_KEY first; neither has a default."
        ),
    )
    serve.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    serve.add_argument("--portfolio", type=Path, default=TIERS_PATH)
    serve.add_argument("--campaign-dir", type=Path, default=CAMPAIGN_DIR)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(handler=run_serve)

    sequence = commands.add_parser(
        "sequence-benchmark",
        help="Compare a Keras LSTM with the champion on the frozen test (ticket T12).",
        description=(
            "Trains an LSTM over the two monthly steps of each window, calibrates it on "
            "validation customers and scores the frozen test window once. Needs the "
            "experiments group: `uv sync --group experiments`."
        ),
    )
    sequence.add_argument("--data-dir", type=Path, default=PROCESSED_DIR / "all")
    sequence.add_argument("--report", type=Path, default=REPORTS_DIR / "sequence_benchmark.md")
    sequence.add_argument("--seed", type=int, default=42)
    sequence.set_defaults(handler=run_sequence_benchmark)

    check_integration = commands.add_parser(
        "check-integration",
        help="Call a running service the way the chatbot and the copilot do (ticket T20).",
        description=(
            "Runs the example client of `client.py` against a running service, including "
            "the refusals every consumer has to handle, and prints what came back. Set "
            "the same two keys the service was started with."
        ),
    )
    check_integration.add_argument("--url", default="http://127.0.0.1:8000")
    check_integration.add_argument(
        "--subscriber-id",
        required=True,
        help="A subscriber to look up; one with no approved offer shows the 404 path.",
    )
    check_integration.add_argument("--output", type=Path, default=None)
    check_integration.set_defaults(handler=run_check_integration)

    return parser


def main(argv: list[str] | None = None) -> None:
    from prepaid_churn.almadar import InvalidCatalogueError
    from prepaid_churn.bundle import BundleError
    from prepaid_churn.client import ServiceError
    from prepaid_churn.retention import RetentionError
    from prepaid_churn.schema import InvalidExportError
    from prepaid_churn.service import ServiceConfigurationError
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
        ImportError,
        InvalidExportError,
        BundleError,
        InvalidCatalogueError,
        ValueModelError,
        RetentionError,
        ServiceConfigurationError,
        ServiceError,
    ) as error:
        parser.exit(1, f"error: {error}\n")
