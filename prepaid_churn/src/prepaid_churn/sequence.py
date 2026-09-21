"""T12 sequence benchmark: a Keras LSTM over the monthly steps of each window.

Why this exists: the syllabus covers recurrent networks (chapters 8 and 9), and the
honest way to cover them is to run one against the champion on the same frozen test
rather than to describe one in a slide.

What it compares. The LSTM reads the two monthly steps of a window as a sequence, so it
sees `prev_<base>` at step 1 and `cur_<base>` at step 2 and has to learn the movement
between them itself. LightGBM never sees a sequence; it gets those same two months side
by side plus the T5 features, which state the movement explicitly (`diff_*`, `trend_*`).
So this is a fair question with a predictable answer: with two steps, a difference is
one subtraction, and a model that is told the difference should beat a model that has to
learn it. Two steps is not a sequence in any useful sense, and the point of running it is
to be able to say that with a number.

Nothing here changes a T7 choice. The architecture, the epochs and the calibrator are
chosen on validation customers, the frozen champion is not touched, and the test window
is read once at the end, exactly as T7 read it (decisions 6 and 13).
"""

import os

import numpy as np
import pandas as pd

from prepaid_churn import evaluation
from prepaid_churn.evaluation import (
    CAPTURE_SHARE,
    choose_calibrator,
    metrics,
    success_thresholds,
    top_share_metrics,
)
from prepaid_churn.windows import LABEL, TENURE_FEATURE

SEED = 42
UNITS = 32
DROPOUT = 0.2
BATCH_SIZE = 256
MAX_EPOCHS = 50
PATIENCE = 5
STEPS = ("prev", "cur")
MODEL_NAME = "lstm"


def sequence_bases(frame: pd.DataFrame) -> list[str]:
    """Measures present in both monthly steps, in a stable order.

    The T5 features are deliberately left out. They are the movement between the two
    months, already computed; handing them to the LSTM as well would make the comparison
    meaningless, because the sequence model would be reading the answer it is supposed to
    derive.
    """
    steps = [
        {name.split("_", 1)[1] for name in frame.columns if name.startswith(f"{step}_")}
        for step in STEPS
    ]
    return sorted(steps[0] & steps[1])


def raw_sequences(frame: pd.DataFrame, bases: list[str]) -> np.ndarray:
    """(customers, 2 steps, measures + tenure), in the order `bases` gives.

    Tenure is one number per customer rather than per month, so it is repeated on both
    steps. That is the usual way to give a recurrent model a static field, and it costs
    the model nothing to ignore it.
    """
    steps = [
        np.column_stack(
            [frame[f"{step}_{base}"].to_numpy(dtype=float) for base in bases]
            + [frame[TENURE_FEATURE].to_numpy(dtype=float)]
        )
        for step in STEPS
    ]
    return np.stack(steps, axis=1)


def fit_standardiser(sequences: np.ndarray) -> dict:
    """Median for missing values, then mean and spread, all from training customers only."""
    flat = sequences.reshape(-1, sequences.shape[-1])
    median = np.nanmedian(flat, axis=0)
    median = np.where(np.isnan(median), 0.0, median)
    filled = np.where(np.isnan(flat), median, flat)
    spread = filled.std(axis=0)
    return {
        "median": median,
        "mean": filled.mean(axis=0),
        "spread": np.where(spread == 0, 1.0, spread),
    }


def standardise(sequences: np.ndarray, standardiser: dict) -> np.ndarray:
    """Fill missing values and put every measure on the same scale.

    LightGBM splits on missing values natively; a neural network cannot see a NaN at all,
    so this step is part of the model, not part of the data, and it is fitted on training
    customers only.
    """
    filled = np.where(np.isnan(sequences), standardiser["median"], sequences)
    return (filled - standardiser["mean"]) / standardiser["spread"]


def build_model(measures: int, seed: int = SEED):
    """One LSTM layer and a probability. Small on purpose: 2 steps carry little to model."""
    keras = _keras()
    keras.utils.set_random_seed(seed)
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(len(STEPS), measures)),
            keras.layers.LSTM(UNITS, dropout=DROPOUT),
            keras.layers.Dense(1, activation="sigmoid"),
        ],
        name="sequence",
    )
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss="binary_crossentropy")
    return model


def _keras():
    """Import Keras on the torch backend, and say what to run when it is not installed."""
    os.environ.setdefault("KERAS_BACKEND", "torch")
    try:
        import keras
    except ImportError as error:
        raise ImportError("T12 needs Keras. Run `uv sync --group experiments` first.") from error
    return keras


def train_sequence(train: pd.DataFrame, validation: pd.DataFrame, seed: int = SEED) -> dict:
    """Fit the LSTM on training customers, stopping on the validation customers.

    Class weights balance the two classes, because churn is about 4% of the rows and an
    unweighted network on that base learns to answer "no" to everything. LightGBM was
    trained without them; the difference is deliberate, and it is the kind of thing the
    calibration step below exists to absorb.
    """
    keras = _keras()
    bases = sequence_bases(train)
    standardiser = fit_standardiser(raw_sequences(train, bases))
    x_train = standardise(raw_sequences(train, bases), standardiser)
    x_validation = standardise(raw_sequences(validation, bases), standardiser)
    y_train, y_validation = train[LABEL].to_numpy(), validation[LABEL].to_numpy()
    positives = y_train.mean()
    model = build_model(x_train.shape[-1], seed)
    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_validation, y_validation),
        epochs=MAX_EPOCHS,
        batch_size=BATCH_SIZE,
        class_weight={0: 1.0, 1: float((1 - positives) / positives)},
        callbacks=[
            keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=PATIENCE, restore_best_weights=True
            )
        ],
        verbose=0,
    )
    return {
        "model": model,
        "bases": bases,
        "standardiser": standardiser,
        "epochs": len(history.history["loss"]),
        "best_epoch": int(np.argmin(history.history["val_loss"])) + 1,
    }


def predict(fitted: dict, frame: pd.DataFrame) -> np.ndarray:
    """Raw probabilities for a frame, in its row order."""
    sequences = standardise(raw_sequences(frame, fitted["bases"]), fitted["standardiser"])
    return fitted["model"].predict(sequences, batch_size=BATCH_SIZE, verbose=0).reshape(-1)


def benchmark(
    datasets: dict[str, pd.DataFrame], gate: dict, baseline_model=None, seed: int = SEED
) -> dict:
    """Train, calibrate on validation the way T7 did, then score the frozen test once.

    `baseline_model` is the saved logistic regression. It is recalibrated here rather than
    read from the gate, because the third success threshold compares two models on the
    same rows and needs the baseline's probabilities, not its score. Recalibrating repeats
    exactly what `freeze` did and chooses nothing new.
    """
    fitted = train_sequence(datasets["train"], datasets["validation"], seed)
    validation, test = datasets["validation"], datasets["test"]
    y_validation, y_test = validation[LABEL], test[LABEL]
    calibrator, calibration = choose_calibrator(predict(fitted, validation), y_validation)
    calibrated = calibrator.transform(predict(fitted, test))
    baseline_probability = None
    if baseline_model is not None:
        baseline_calibrator, _ = choose_calibrator(
            evaluation.predict(baseline_model, validation), y_validation
        )
        baseline_probability = baseline_calibrator.transform(
            evaluation.predict(baseline_model, test)
        )
    return {
        "fitted": fitted,
        "calibrator": calibrator.method,
        "calibration_log_loss": min(calibration.values()),
        "test_metrics": metrics(y_test, calibrated),
        "capture": float(top_share_metrics(calibrated, y_test, (CAPTURE_SHARE,))["recall"].iloc[0]),
        "thresholds": success_thresholds(y_test, calibrated, baseline_probability),
        "baseline_pr_auc": gate.get("test_metrics", {})
        .get("logistic_regression", {})
        .get("pr_auc"),
    }


METRIC_LABELS = {
    "pr_auc": "PR-AUC (primary)",
    "roc_auc": "ROC-AUC",
    "log_loss": "Log loss",
    "brier": "Brier",
    "mean_probability": "Mean predicted",
    "churn_rate": "Observed churn rate",
}


def benchmark_report(result: dict, gate: dict, datasets: dict[str, pd.DataFrame]) -> str:
    """The comparison table and the verdict, for `reports/sequence_benchmark.md`."""
    champion = gate.get("champion", "lightgbm")
    test_metrics = dict(gate.get("test_metrics", {}))
    test_metrics[MODEL_NAME] = result["test_metrics"]
    names = [name for name in test_metrics if name != MODEL_NAME] + [MODEL_NAME]
    fitted = result["fitted"]
    lines = [
        "# T12 sequence benchmark",
        "",
        "Generated by `uv run churn sequence-benchmark` (ticket T12).",
        "",
        f"A Keras LSTM ({UNITS} units, dropout {DROPOUT}, Adam, batch {BATCH_SIZE}) reads the "
        f"two monthly steps of each window as a sequence of {len(fitted['bases'])} measures "
        "plus tenure.",
        "It is trained on the same training customers, stopped on the same validation "
        "customers, calibrated the same way, and scored once on the same frozen test window "
        "as T7.",
        "No T7 choice was changed, and the champion was not retrained.",
        "",
        "## The same test window, three models",
        "",
        "| Metric | " + " | ".join(names) + " |",
        "|---" * (len(names) + 1) + "|",
    ]
    for metric, label in METRIC_LABELS.items():
        values = []
        for name in names:
            value = test_metrics.get(name, {}).get(metric)
            values.append("n/a" if value is None else f"{float(value):.4f}")
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    capture = gate.get("thresholds", {}).get("capture", {}).get("value")
    champion_capture = "n/a" if capture is None else f"{float(capture):.4f}"
    lines += [
        f"| Capture at {int(CAPTURE_SHARE * 100)}% | "
        + " | ".join(
            (
                f"{result['capture']:.4f}"
                if name == MODEL_NAME
                else (champion_capture if name == champion else "n/a")
            )
            for name in names
        )
        + " |",
        "",
        f"Training: stopped after {fitted['epochs']} epochs, best validation loss at epoch "
        f"{fitted['best_epoch']}; calibrated with {result['calibrator']} "
        f"(validation log loss {result['calibration_log_loss']:.4f}).",
        f"Rows: {len(datasets['train'])} train, {len(datasets['validation'])} validation, "
        f"{len(datasets['test'])} test.",
        f"Seed {SEED} through `keras.utils.set_random_seed`, on the torch backend; the same "
        "machine reproduces this table, and another one can differ in the last digits.",
        "",
        "## Would this model be released?",
        "",
        "The four success thresholds of decision 13, applied to the LSTM:",
        "",
        "| Check | Value | Required | Passed |",
        "|---|---|---|---|",
    ]
    for check in result["thresholds"].values():
        value = check.get("value")
        shown = "n/a" if value is None else f"{float(value):.4f}"
        lines.append(
            f"| {check['description']} | {shown} | {check['required']} | "
            f"{'yes' if check['passed'] else 'no'} |"
        )
    failed = [check for check in result["thresholds"].values() if not check["passed"]]
    lines += [
        "",
        f"**{'Yes' if not failed else 'No'}**: it "
        + (
            "passes all four checks, which is not the same as being better than the champion."
            if not failed
            else f"fails {len(failed)} of the four, so it would not be released (decision 13)."
        ),
        "",
        "## Verdict",
        "",
        _verdict(result, test_metrics, champion),
        "",
        "## What this does not settle",
        "",
        "- Two monthly steps are not a sequence. With six or twelve months per customer the "
        "comparison would be worth running again, and the recurrent model would have "
        "something to remember.",
        "- The upGrad export has one row per customer per month, so nothing finer than a "
        "month can be modelled here. Call-detail records would change that, and they are "
        "not in this data.",
        "- The frozen champion stays the champion whatever this table says: the test window "
        "was spent once in T7, and choosing a model on it now would be the mistake decision "
        "6 exists to prevent.",
    ]
    return "\n".join(line for line in lines if line is not None) + "\n"


def _baseline_note(result: dict) -> str:
    """The sharper half of the verdict: it also lost to the simplest model in the module."""
    baseline = result["baseline_pr_auc"]
    if baseline is None or result["test_metrics"]["pr_auc"] >= float(baseline):
        return ""
    return (
        f" It also lands below the logistic regression baseline ({float(baseline):.4f}), which "
        "is the check a new model has to clear before anyone discusses architecture."
    )


def _verdict(result: dict, test_metrics: dict, champion: str) -> str:
    lstm = result["test_metrics"]["pr_auc"]
    best = test_metrics.get(champion, {}).get("pr_auc")
    if best is None:
        return f"The LSTM reaches a test PR-AUC of {lstm:.4f}; no champion figure was available."
    gap = (lstm - best) / best * 100
    if lstm < best:
        return (
            f"LightGBM wins, as expected: PR-AUC {best:.4f} against the LSTM's {lstm:.4f}, "
            f"{abs(gap):.1f}% lower. With two monthly steps the movement between them is one "
            "subtraction, the T5 features hand it to LightGBM directly, and the LSTM has to "
            "learn it from 2 timesteps and a small number of churners. The recurrent "
            "architecture has nothing to remember here, so it is the wrong tool for this "
            "data shape, not a badly tuned one."
        ) + _baseline_note(result)
    return (
        f"The LSTM reaches a test PR-AUC of {lstm:.4f} against LightGBM's {best:.4f}, "
        f"{gap:.1f}% higher. That is the opposite of what two monthly steps predict, so "
        "treat it as a result to reproduce before acting on it: rerun with another seed, and "
        "check the calibration and the capture row above before anyone calls it a better "
        "model. The champion does not change here in any case (decision 6)."
    )
