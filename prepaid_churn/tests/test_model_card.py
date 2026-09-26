"""The model card is indexed by the employee copilot (decision 17), so its figures must
not drift away from the reports they came from.

These tests read the committed card and the committed reports and compare them.
They use no model and no dataset: a stale number in a document the copilot quotes is a
documentation bug, and this is the cheapest place to catch it.
"""

import re

import pytest

from prepaid_churn.data import PROJECT_ROOT

CARD_PATH = PROJECT_ROOT / "docs" / "model_card.md"
REPORTS = PROJECT_ROOT / "reports"
BUNDLE_VERSION = "lightgbm-2026-09-19-ef9430fb"


@pytest.fixture(scope="module")
def card() -> str:
    return CARD_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def evaluation() -> str:
    return (REPORTS / "evaluation_all.md").read_text(encoding="utf-8")


def test_the_card_exists_and_names_the_frozen_bundle(card):
    assert card.startswith("# Model card")
    assert card.count(BUNDLE_VERSION) >= 2  # the header table and the sources table


@pytest.mark.parametrize(
    ("figure", "what"),
    [
        ("0.3477", "test PR-AUC, the primary metric"),
        ("0.8910", "test ROC-AUC"),
        ("0.2770", "the logistic regression PR-AUC it must beat"),
        ("0.6152", "share of churners in the riskiest tenth"),
        ("0.0013", "calibration gap"),
        ("7.9922", "PR-AUC over the churn rate"),
        ("0.2511", "high-risk threshold"),
        ("0.0461", "medium-risk threshold and the validation churn rate"),
    ],
)
def test_every_headline_figure_is_in_the_report_it_cites(card, evaluation, figure, what):
    assert figure in evaluation, f"{what} is no longer in evaluation_all.md"
    assert figure in card, f"{what} is missing from the model card"


def test_the_split_sizes_match_the_dataset_report(card):
    dataset = (REPORTS / "dataset_all.md").read_text(encoding="utf-8")
    for rows, formatted in (("45858", "45,858"), ("9812", "9,812"), ("9677", "9,677")):
        assert rows in dataset
        assert formatted in card
    assert "126" in dataset and "126" in card  # feature columns


def test_the_validation_to_test_gap_is_quoted_from_both_reports(card):
    training = (REPORTS / "training_all.md").read_text(encoding="utf-8")
    assert "0.4582" in training, "validation PR-AUC changed"
    assert "0.4582" in card, "the card must keep showing what selection costs"


def test_the_quoted_uncertainty_ranges_are_in_their_report(card):
    uncertainty = (REPORTS / "uncertainty.md").read_text(encoding="utf-8")
    for figure in ("0.3006", "0.4000", "0.5725", "0.6582"):  # PR-AUC and capture, 95% ranges
        assert figure in uncertainty, f"{figure} is no longer in uncertainty.md"
        assert figure in card, f"{figure} is missing from the model card"


def test_the_operator_assumptions_match_their_report(card):
    view = (REPORTS / "operator_view.md").read_text(encoding="utf-8")
    for figure in ("70 LYD", "537.17", "0.130313", "68.94"):
        assert figure in view, f"{figure} is no longer in operator_view.md"
        assert figure in card, f"{figure} is missing from the model card"


def test_every_file_the_sources_table_names_exists(card):
    sources = card.split("## Sources", 1)[1]
    named = set(re.findall(r"`((?:reports|docs)/[a-z_]+\.md)`", sources))
    assert len(named) >= 9, f"the sources table lost entries: {sorted(named)}"
    missing = [name for name in named if not (PROJECT_ROOT / name).exists()]
    assert not missing, f"the card cites files that do not exist: {missing}"


def test_the_card_states_what_the_model_may_not_be_used_for(card):
    """The out-of-scope section is the one an evaluator reads hardest."""
    scope = card.split("## Out-of-scope use", 1)[1].split("## Training data", 1)[0]
    for rule in ("pricing", "credit", "sold", "named reviewer"):
        assert rule in scope.lower(), f"the out-of-scope section no longer mentions {rule}"


def test_the_card_keeps_its_limitations_and_ethics_sections(card):
    for heading in (
        "## Intended use",
        "## Out-of-scope use",
        "## Training data",
        "## Metrics",
        "## Calibration",
        "## Explainability",
        "## The human approval step",
        "## Limitations",
        "## Ethical considerations",
        "## Selection bias",
        "## Maintenance",
        "## Sources",
    ):
        assert heading in card, f"the model card lost {heading}"


def test_the_readme_links_the_card_and_the_card_is_reachable():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/model_card.md" in readme
