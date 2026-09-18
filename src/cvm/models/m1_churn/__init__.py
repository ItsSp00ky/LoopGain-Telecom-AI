"""M1 -- Silent Churn Engine.

Deliberately structured as an EXPERIMENT rather than a single model, because
the experiment is more informative than either arm alone.

    Arm A  LightGBM on ~80 engineered features
    Arm B  LSTM on raw 90-day daily sequences

Either outcome is a result. If the LSTM wins, sequential structure carries
information our features discard, and we say so. If LightGBM wins -- the
likelier outcome on short sparse prepaid histories -- we explain why: 90
timesteps of mostly-zero daily activity is a weak sequence signal, gradient
boosting is extremely strong on tabular data, and the engineered decay ratios
already encode most of the temporal information.

Demonstrating an informed architecture choice is a stronger technical signal
than defaulting to a neural network because it sounds advanced. The BENCHMARK
is the deliverable, not the winner.
"""