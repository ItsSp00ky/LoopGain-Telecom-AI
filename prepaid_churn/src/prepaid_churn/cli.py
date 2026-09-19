"""Command-line entry point. Each pipeline stage adds one subcommand here."""

import argparse
from pathlib import Path

from prepaid_churn.data import PROJECT_ROOT, RAW_TRAIN_PATH, REPORTS_DIR, load_raw

CONTRACT_PATH = PROJECT_ROOT / "docs" / "data_contract.md"


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
    build.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data" / "processed")
    build.add_argument("--report", type=Path, default=None)
    build.add_argument(
        "--high-value", action="store_true", help="Keep only the top 30%% by recharge amount."
    )
    build.set_defaults(handler=run_build_dataset)

    return parser


def main(argv: list[str] | None = None) -> None:
    from prepaid_churn.schema import InvalidExportError

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return
    try:
        args.handler(args)
    except (FileNotFoundError, InvalidExportError) as error:
        parser.exit(1, f"error: {error}\n")
