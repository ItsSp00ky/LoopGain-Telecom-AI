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
