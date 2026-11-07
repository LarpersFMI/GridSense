"""LEAR: Lasso-estimated autoregressive model, the standard day-ahead price benchmark. Owner: ML-P.

One Lasso per (horizon, local hour of the target). Inputs: the full 24-hour price vectors of the
issue day D and of the day 7 days before the target (both known at issue time), plus every `f_`
feature of the row. Prices are asinh-transformed. As in epftoolbox, LARS with AIC picks the
penalty and a coordinate-descent Lasso refits with it (stable with correlated inputs).
"""

import warnings
from dataclasses import dataclass, field
from typing import ClassVar, Literal

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Lasso, LassoLarsIC
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from gridsense import config
from gridsense.models.base import OUTPUT_COLUMNS, PRICE_COLUMNS, feature_columns
from gridsense.models.baselines import NAIVE_COLUMN, PERSISTENCE_COLUMN
from gridsense.schemas import FEATURE_PREFIX

HOUR = f"{FEATURE_PREFIX}hour"
# Substrings marking columns measured in €/MWh, which get the same asinh transform as the target.
PRICE_LIKE = ("price", f"{FEATURE_PREFIX}d_", "midday_min", "mean_30d")
# Already inside the 24-hour vectors; exact duplicates destabilise LARS.
DUPLICATED = (PERSISTENCE_COLUMN, NAIVE_COLUMN)
# How far (in asinh units) predictions may go beyond the training range; sinh explodes otherwise.
CLIP_MARGIN = 1.0


def _price_vectors(table: pd.DataFrame, column: str, index: list[str], prefix: str) -> pd.DataFrame:
    wide = table.pivot_table(index=index, columns=HOUR, values=column, aggfunc="mean")
    wide = wide.reindex(columns=range(24))
    wide.columns = [f"{prefix}_h{h}" for h in range(24)]
    return wide


def _fit_lear(X: pd.DataFrame, z: pd.Series, criterion: str) -> Pipeline:
    prep = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler())
    Xs = prep.fit_transform(X)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        alpha = LassoLarsIC(criterion=criterion).fit(Xs, z).alpha_
        lasso = Lasso(alpha=max(alpha, 1e-4), max_iter=10_000).fit(Xs, z)
    return Pipeline([*prep.steps, ("lasso", lasso)])


@dataclass
class LEAR:
    name: ClassVar[str] = "lear"
    criterion: Literal["aic", "bic"] = "aic"
    center: float = field(default=0.0, init=False)
    scale: float = field(default=1.0, init=False)
    z_range: tuple[float, float] = field(default=(-np.inf, np.inf), init=False)
    columns: list[str] = field(default_factory=list, init=False)
    models: dict = field(default_factory=dict, init=False)
    offsets: dict = field(default_factory=dict, init=False)

    def _asinh(self, x):
        return np.arcsinh((x - self.center) / self.scale)

    def _price(self, z):
        return self.center + self.scale * np.sinh(z)

    def _design(self, table: pd.DataFrame) -> pd.DataFrame:
        day_d = _price_vectors(table, PERSISTENCE_COLUMN, ["issue_ts"], "price_d")
        week_before = _price_vectors(table, NAIVE_COLUMN, ["issue_ts", "horizon_days"], "price_m7")
        X = (
            table[["issue_ts", "horizon_days"]]
            .join(day_d, on="issue_ts")
            .join(week_before, on=["issue_ts", "horizon_days"])
            .drop(columns=["issue_ts", "horizon_days"])
            .join(table[[c for c in feature_columns(table) if c not in DUPLICATED]])
        )
        price_cols = [c for c in X.columns if any(token in c for token in PRICE_LIKE)]
        X[price_cols] = self._asinh(X[price_cols])
        return X

    def _groups(self, table: pd.DataFrame):
        return table.groupby(["horizon_days", HOUR]).groups.items()

    def _predict_median(self, table: pd.DataFrame) -> pd.Series:
        X = self._design(table).reindex(columns=self.columns)
        out = pd.Series(np.nan, index=table.index)
        for key, idx in self._groups(table):
            if key in self.models:
                z = np.clip(self.models[key].predict(X.loc[idx]), *self.z_range)
                out.loc[idx] = self._price(z)
        return out

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "LEAR":
        y = train["y_price"]
        self.center = float(y.median())
        self.scale = max(float((y - self.center).abs().median()), 1.0)
        X = self._design(train)
        self.columns = list(X.columns)
        z = self._asinh(y)
        self.z_range = (float(z.min()) - CLIP_MARGIN, float(z.max()) + CLIP_MARGIN)
        for key, idx in self._groups(train):
            self.models[key] = _fit_lear(X.loc[idx], z.loc[idx], self.criterion)

        # Interval from out-of-sample residuals when val is given, like the LightGBM conformal step.
        calib = val if val is not None else train
        resid = calib["y_price"] - self._predict_median(calib)
        for key, r in resid.groupby([calib["horizon_days"], calib[HOUR]]):
            r = r.dropna()
            if len(r):
                self.offsets[key] = np.quantile(r, config.QUANTILES)
        return self

    def predict(self, table: pd.DataFrame) -> pd.DataFrame:
        p50 = self._predict_median(table).to_numpy()
        missing = np.full(len(config.QUANTILES), np.nan)
        offsets = np.array(
            [self.offsets.get(key, missing) for key in zip(table["horizon_days"], table[HOUR])]
        )
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        out[list(PRICE_COLUMNS)] = np.sort(p50[:, None] + offsets, axis=1)
        return out
