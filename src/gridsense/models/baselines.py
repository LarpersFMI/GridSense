from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.models.base import OUTPUT_COLUMNS, PRICE_COLUMNS
from gridsense.schemas import FEATURE_PREFIX

NAIVE_COLUMN = f"{FEATURE_PREFIX}price_same_hour_target_m7"
PERSISTENCE_COLUMN = f"{FEATURE_PREFIX}price_same_hour_d"


@dataclass
class SeasonalNaivePrice:
    """P50 = price at the same hour 7 days before the target (known at issue time for h <= 7).

    P10/P90 add the train residual quantiles of that horizon.
    """

    name: ClassVar[str] = "seasonal_naive"
    column: ClassVar[str] = NAIVE_COLUMN
    offsets: pd.DataFrame = field(default=None, init=False)

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "SeasonalNaivePrice":
        resid = (train["y_price"] - train[self.column]).dropna()
        horizon = train.loc[resid.index, "horizon_days"]
        self.offsets = resid.groupby(horizon).quantile(list(config.QUANTILES)).unstack()
        self.offsets.columns = list(PRICE_COLUMNS)
        return self

    def predict(self, table: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        offsets = self.offsets.reindex(table["horizon_days"]).to_numpy()
        out[list(PRICE_COLUMNS)] = table[[self.column]].to_numpy() + offsets
        return out


@dataclass
class PersistencePrice(SeasonalNaivePrice):
    """P50 = price at the same hour on the issue day D; strongest naive forecast at D+1."""

    name: ClassVar[str] = "persistence"
    column: ClassVar[str] = PERSISTENCE_COLUMN


def climatology(train: pd.DataFrame, table: pd.DataFrame) -> pd.Series:
    """P(cheap) by month x weekday x hour, fitted on train only."""
    raise NotImplementedError


def solar_rule(table: pd.DataFrame, irradiance_threshold: float) -> pd.Series:
    raise NotImplementedError
