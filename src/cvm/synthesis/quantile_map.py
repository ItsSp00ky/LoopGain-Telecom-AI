"""Map real monetary fields onto the Libyan scale by quantile.

The Iranian `Charge Amount` field is ordinal 0-9. Mapping it by quantile onto
the LYD scratch-card ladder means a 90th-percentile spender lands on 50-100 LYD
cards rather than 5 LYD -- preserving the rank structure the GAN learned while
changing the units to ones a Libyan evaluator recognises.
"""

from __future__ import annotations

import pandas as pd

RECHARGE_DENOMINATIONS_LYD = (5, 10, 15, 20, 25, 50, 100)


def map_to_lyd_ladder(ordinal: pd.Series) -> pd.Series:
    """Quantile-map an ordinal spend field onto the scratch-card ladder."""
    raise NotImplementedError("TODO(E1)")