from typing import Protocol

import pandas as pd

from gridsense.schemas import FEATURE_PREFIX

OUTPUT_COLUMNS = ("p_near_zero", "p_cheap", "price_p10", "price_p50", "price_p90")


def feature_columns(table: pd.DataFrame) -> list[str]:
    return [c for c in table.columns if c.startswith(FEATURE_PREFIX)]


class Forecaster(Protocol):
    """Common interface for baselines and models so evaluate.py can compare them all.

    predict() returns OUTPUT_COLUMNS aligned to the input rows; outputs a model
    doesn't produce are NaN.
    """

    name: str

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "Forecaster": ...

    def predict(self, table: pd.DataFrame) -> pd.DataFrame: ...
