import numpy as np
import pytest

from prepaid_churn.training import (
    evaluation_table,
    feature_columns,
    predict,
    signed_log1p,
    train_models,
    training_report,
)
from prepaid_churn.windows import build_datasets


@pytest.fixture
def datasets(population):
    return build_datasets(population)


def test_feature_columns_exclude_id_and_label(datasets):
    columns = feature_columns(datasets["train"])
    assert "id" not in columns
    assert "churn" not in columns
    assert "tenure_days" in columns


def test_signed_log1p_keeps_sign_and_order():
    values = np.array([-100.0, -1.0, 0.0, 1.0, 100.0])
    transformed = signed_log1p(values)
    assert transformed[2] == 0
    assert np.all(np.diff(transformed) > 0)


def test_both_models_train_and_predict_probabilities(datasets):
    models = train_models(datasets["train"])
    assert set(models) == {"logistic_regression", "lightgbm"}
    for model in models.values():
        probability = predict(model, datasets["validation"])
        assert probability.shape == (len(datasets["validation"]),)
        assert np.all((probability >= 0) & (probability <= 1))


def test_training_is_reproducible(datasets):
    first = train_models(datasets["train"])
    second = train_models(datasets["train"])
    for name in first:
        np.testing.assert_array_equal(
            predict(first[name], datasets["validation"]),
            predict(second[name], datasets["validation"]),
        )


def test_report_lists_both_models(datasets):
    models = train_models(datasets["train"])
    table = evaluation_table(models, datasets["validation"])
    assert list(table.index) == ["logistic_regression", "lightgbm"]
    report = training_report(models, datasets["train"], datasets["validation"])
    assert "| lightgbm |" in report
    assert "top features" in report
