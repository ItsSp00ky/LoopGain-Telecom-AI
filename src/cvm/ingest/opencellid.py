"""Dataset D -- OpenCelliD, filtered to MCC 606 / MNC 01.  Owner: E1

MNC 01 is Almadar Aljadid, the operator this project models. Yields real
Libyan tower identifiers with coordinates, used to give every generated
subscriber a genuine home_cell_id in a genuine district.

Licence is CC BY-SA -- attribution is required wherever the map appears,
including in the pitch deck.
"""

from __future__ import annotations

import pandas as pd


def fetch(mcc: int = 606, mncs: tuple[str, ...] = ("01",)) -> pd.DataFrame:
    """Pull the Almadar (MNC 01) extract. Needs OPENCELLID_API_KEY."""
    raise NotImplementedError("TODO(E1)")


def assign_districts(sites: pd.DataFrame) -> pd.DataFrame:
    """Label each site with its Libyan district from its coordinates.

    District is a NETWORK-QUALITY input only. It must never reach the pricing
    engine as a socioeconomic lever -- see conf/pricing.yaml#fairness.
    """
    raise NotImplementedError("TODO(E1)")