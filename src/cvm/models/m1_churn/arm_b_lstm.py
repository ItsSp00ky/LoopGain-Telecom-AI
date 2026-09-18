"""Arm B -- LSTM on raw daily sequences.  Owner: E2

    Input (90, k) -> Masking -> LSTM(64) -> Dropout(0.3) -> LSTM(32)
                  -> Dense(16, relu) -> Dense(1, sigmoid)

Input is raw daily recharge, data, voice and SMS. NO hand aggregation -- the
point is whether the network learns the decay patterns we engineered by hand.

Two things the write-up should state in words rather than leave implied:

* Overfitting is controlled by dropout and early stopping, not by hope.
* Vanishing gradients are why this is an LSTM and not a plain RNN -- gating is
  the mechanism that lets gradient survive 90 timesteps.

Trains on a free Colab T4. Checkpoint to Drive every epoch: Colab sessions get
cut, and this is the risk-register mitigation.
"""

from __future__ import annotations

import numpy as np


def build_model(input_shape: tuple[int, int]):
    raise NotImplementedError("TODO(E2)")


def train(X: np.ndarray, y: np.ndarray, X_val: np.ndarray, y_val: np.ndarray, **kwargs):
    """Fit with EarlyStopping, ReduceLROnPlateau, ModelCheckpoint, TensorBoard."""
    raise NotImplementedError("TODO(E2)")


def export_savedmodel(model, path: str) -> None:
    """Save for CPU-only serving. This is what ships back from Colab."""
    raise NotImplementedError("TODO(E2)")