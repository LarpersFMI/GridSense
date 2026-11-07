from typing import Protocol

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.schemas import FEATURE_PREFIX

PROBA_COLUMNS = ("p_near_zero", "p_cheap")
PRICE_COLUMNS = tuple(f"price_p{round(q * 100)}" for q in config.QUANTILES)
OUTPUT_COLUMNS = PROBA_COLUMNS + PRICE_COLUMNS


def feature_columns(table: pd.DataFrame) -> list[str]:
    cols = [c for c in table.columns if c.startswith(FEATURE_PREFIX)]
    if not cols:
        raise ValueError(f"no feature columns starting with {FEATURE_PREFIX!r}")
    return cols


def recency_weights(table: pd.DataFrame, half_life_days: float | None) -> np.ndarray | None:
    if half_life_days is None:
        return None
    ts = table["target_ts_utc"]
    age_days = (ts.max() - ts).dt.total_seconds().to_numpy() / 86400
    return 0.5 ** (age_days / half_life_days)


class Forecaster(Protocol):
    """Common interface for baselines and models so evaluate.py can compare them all.

    predict() returns OUTPUT_COLUMNS aligned to the input rows; outputs a model
    doesn't produce are NaN.
    """

    name: str

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "Forecaster": ...

    def predict(self, table: pd.DataFrame) -> pd.DataFrame: ...
