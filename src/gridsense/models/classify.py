"""Low-price classification: P(price <= 20) and P(price <= 0) per hour. Owner: ML classification."""

from dataclasses import dataclass, field
from typing import ClassVar

import lightgbm as lgb
import numpy as np
import pandas as pd

from gridsense import config
from gridsense.models.base import OUTPUT_COLUMNS, feature_columns, recency_weights

LABELS = {"p_near_zero": "y_near_zero", "p_cheap": "y_cheap"}

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
class LowPriceClassifier:
    name: ClassVar[str] = "lgbm_classifier"
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    half_life_days: float | None = 365.0
    early_stopping_rounds: int = 100
    features: list[str] = field(default_factory=list, init=False)
    models: dict[str, lgb.LGBMClassifier] = field(default_factory=dict, init=False)

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "LowPriceClassifier":
        self.features = feature_columns(train)
        weights = recency_weights(train, self.half_life_days)
        for out, label in LABELS.items():
            y = train[label].astype(int)
            if y.nunique() < 2:
                raise ValueError(f"{label} has a single class in train; can't fit {out}")
            model = lgb.LGBMClassifier(**self.params)
            fit_kwargs = {}
            if val is not None:
                fit_kwargs = {
                    "eval_X": (val[self.features],),
                    "eval_y": (val[label].astype(int),),
                    "eval_metric": "average_precision",
                    "callbacks": [lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
                }
            model.fit(train[self.features], y, sample_weight=weights, **fit_kwargs)
            self.models[out] = model
        return self

    def predict(self, table: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        for col, model in self.models.items():
            out[col] = model.predict_proba(table[self.features])[:, 1]
        return out

    def best_iterations(self) -> dict[str, int]:
        return {col: int(m.best_iteration_ or m.n_estimators) for col, m in self.models.items()}
