"""Price forecasting: P10/P50/P90 of the hourly price. Owner: ML price forecasting."""

from dataclasses import dataclass, field
from typing import ClassVar

import lightgbm as lgb
import numpy as np
import pandas as pd

from gridsense import config
from gridsense.models.base import OUTPUT_COLUMNS, PRICE_COLUMNS, feature_columns, recency_weights

DEFAULT_PARAMS = {
    "n_estimators": 2000,
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": config.RANDOM_SEED,
    "verbose": -1,
}


@dataclass
class PriceForecaster:
    name: ClassVar[str] = "lgbm_quantile"
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    quantiles: tuple[float, ...] = config.QUANTILES
    half_life_days: float | None = 365.0
    early_stopping_rounds: int = 100
    features: list[str] = field(default_factory=list, init=False)
    models: dict[float, lgb.LGBMRegressor] = field(default_factory=dict, init=False)

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "PriceForecaster":
        self.features = feature_columns(train)
        weights = recency_weights(train, self.half_life_days)
        for q in self.quantiles:
            model = lgb.LGBMRegressor(objective="quantile", alpha=q, **self.params)
            fit_kwargs = {}
            if val is not None:
                fit_kwargs = {
                    "eval_X": (val[self.features],),
                    "eval_y": (val["y_price"],),
                    "callbacks": [lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
                }
            model.fit(train[self.features], train["y_price"], sample_weight=weights, **fit_kwargs)
            self.models[q] = model
        return self

    def predict(self, table: pd.DataFrame) -> pd.DataFrame:
        raw = np.column_stack([self.models[q].predict(table[self.features]) for q in self.quantiles])
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        # Separate quantile models can cross; sorting restores P10 <= P50 <= P90.
        out[list(PRICE_COLUMNS)] = np.sort(raw, axis=1)
        return out

    def best_iterations(self) -> dict[str, int]:
        return {str(q): int(m.best_iteration_ or m.n_estimators) for q, m in self.models.items()}
