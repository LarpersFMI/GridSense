from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.models.base import OUTPUT_COLUMNS, PRICE_COLUMNS
from gridsense.models.classify import LABELS
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


# --- Classification baselines (ML-C): the simple models LowPriceClassifier has to beat. ---

GHI_COLUMN = f"{FEATURE_PREFIX}ghi_mean"
DAY_OFF_COLUMNS = (f"{FEATURE_PREFIX}is_weekend", f"{FEATURE_PREFIX}is_holiday")
CELL = ["month", "weekday", "hour"]


def _labels(table: pd.DataFrame) -> pd.DataFrame:
    """Both labels as 0/1 floats, named after the probability column each one becomes."""
    y = table[list(LABELS.values())].astype(float)
    y.columns = list(LABELS)
    return y


def _calendar(table: pd.DataFrame) -> pd.DataFrame:
    """Local month, weekday (0 = Monday) and hour of each target hour."""
    local = table["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    return pd.DataFrame(
        {"month": local.dt.month, "weekday": local.dt.day_of_week, "hour": local.dt.hour},
        index=table.index,
    )


@dataclass
class Climatology:
    """P(label) = how often that month x weekday x hour had the label in train. No weather at all.

    A cell holds only ~9 train hours (about 2 years of e.g. Sundays in May at 13:00), so one lucky
    hour would swing it a lot. Each cell is therefore pulled toward its month x hour rate, as if it
    had `prior_hours` extra hours at that rate.
    """

    name: ClassVar[str] = "climatology"
    prior_hours: float = 5.0
    cells: pd.DataFrame = field(default=None, init=False)
    overall: pd.Series = field(default=None, init=False)

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "Climatology":
        # The 7 horizons repeat each target hour with the same label; count every hour once.
        hours = train.drop_duplicates("target_ts_utc")
        data = _calendar(hours).join(_labels(hours))
        cols = list(LABELS)

        month_hour = data.groupby(["month", "hour"])[cols].mean()
        grouped = data.groupby(CELL)[cols]
        sums, counts = grouped.sum(), grouped.count()
        prior = month_hour.reindex(sums.index.droplevel("weekday")).to_numpy()
        self.cells = (sums + self.prior_hours * prior) / (counts + self.prior_hours)
        self.overall = data[cols].mean()
        return self

    def predict(self, table: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        p = self.cells.reindex(pd.MultiIndex.from_frame(_calendar(table)))
        out[list(LABELS)] = p.fillna(self.overall).to_numpy()  # cells never seen in train
        return out


@dataclass
class SolarRule:
    """Expert rule: cheap when forecast sunshine is strong on a weekend or public holiday.

    The rule itself is yes/no. fit() turns it into a probability by looking at how often each label
    was true in train when the rule fired and when it didn't, so it can be scored like the models.
    """

    name: ClassVar[str] = "solar_rule"
    threshold_wm2: float = 500.0
    ghi_column: str = GHI_COLUMN
    day_off_columns: tuple[str, ...] = DAY_OFF_COLUMNS
    rates: pd.DataFrame = field(default=None, init=False)

    def fires(self, table: pd.DataFrame) -> pd.Series:
        missing = [c for c in (self.ghi_column, *self.day_off_columns) if c not in table]
        if missing:
            raise ValueError(f"solar rule needs columns {missing}; was weather_fc in the table?")
        day_off = table[list(self.day_off_columns)].astype(bool).any(axis=1)
        # A missing forecast (NaN) compares as False, so the rule simply doesn't fire.
        return (table[self.ghi_column] >= self.threshold_wm2) & day_off

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "SolarRule":
        y = _labels(train)
        # If the rule never (or always) fires in train, fall back to the overall rate.
        self.rates = y.groupby(self.fires(train)).mean().reindex([False, True]).fillna(y.mean())
        return self

    def predict(self, table: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        # Look up each row's rate by its True/False (reindex, because .loc would filter on it).
        out[list(LABELS)] = self.rates.reindex(self.fires(table)).to_numpy()
        return out
