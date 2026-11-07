"""Price forecasting: P10/P50/P90 of the hourly price. Owner: ML price forecasting."""

from dataclasses import dataclass, field
from typing import ClassVar, Literal

import lightgbm as lgb
import numpy as np
import pandas as pd

from gridsense import config
from gridsense.models.base import OUTPUT_COLUMNS, PRICE_COLUMNS, feature_columns, recency_weights
from gridsense.models.calibrate import conformal_offsets

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

# Extra quantiles give an approximate distribution (e.g. P(price <= 20)); only P10/P50/P90 are exported.
TRAIN_QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
# Trees can't extrapolate across price-level shifts, so they learn the deviation from a recent
# level instead: the first available of these columns per row.
LEVEL_COLUMNS = ("f_price_same_hour_mean_7d", "f_d_mean", "f_mean_30d")


@dataclass
class PriceForecaster:
    name: ClassVar[str] = "lgbm_quantile"
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    quantiles: tuple[float, ...] = TRAIN_QUANTILES
    target_transform: Literal["asinh", "none"] = "asinh"
    conformal: bool = True
    half_life_days: float | None = 365.0
    level_columns: tuple[str, ...] = LEVEL_COLUMNS
    early_stopping_rounds: int = 100
    features: list[str] = field(default_factory=list, init=False)
    models: dict[float, lgb.LGBMRegressor] = field(default_factory=dict, init=False)
    center: float = field(default=0.0, init=False)
    scale: float = field(default=1.0, init=False)
    conformal_offsets: dict[int, float] = field(default_factory=dict, init=False)

    def _to_model_scale(self, y: pd.Series) -> pd.Series:
        if self.target_transform == "none":
            return y
        return np.arcsinh((y - self.center) / self.scale)

    def _to_price(self, z: np.ndarray) -> np.ndarray:
        if self.target_transform == "none":
            return z
        return self.center + self.scale * np.sinh(z)

    def _level(self, table: pd.DataFrame) -> pd.Series:
        """Recent price level per row; 0 (absolute prices) if the table has no level column."""
        columns = [c for c in self.level_columns if c in table]
        level = pd.Series(np.nan if columns else 0.0, index=table.index)
        for col in columns:
            level = level.fillna(table[col])
        return level

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "PriceForecaster":
        self.features = feature_columns(train)
        train = train[self._level(train).notna()]
        y = train["y_price"] - self._level(train)
        self.center = float(y.median())
        self.scale = max(float((y - self.center).abs().median()), 1.0)
        weights = recency_weights(train, self.half_life_days)
        if val is not None:
            val = val[self._level(val).notna()]
        for q in self.quantiles:
            model = lgb.LGBMRegressor(objective="quantile", alpha=q, **self.params)
            fit_kwargs = {}
            if val is not None:
                fit_kwargs = {
                    "eval_X": (val[self.features],),
                    "eval_y": (self._to_model_scale(val["y_price"] - self._level(val)),),
                    "callbacks": [lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
                }
            model.fit(train[self.features], self._to_model_scale(y), sample_weight=weights, **fit_kwargs)
            self.models[q] = model

        if self.conformal and val is not None:
            # Same val as early stopping: slightly optimistic; the test set gives the honest coverage.
            raw = self.predict_quantiles(val)
            lo, hi = min(config.QUANTILES), max(config.QUANTILES)
            self.conformal_offsets = conformal_offsets(
                val["y_price"], raw[lo], raw[hi], val["horizon_days"], coverage=hi - lo
            )
        return self

    def predict_quantiles(self, table: pd.DataFrame) -> pd.DataFrame:
        """All trained quantiles in price units, without conformal adjustment."""
        raw = np.column_stack([self.models[q].predict(table[self.features]) for q in self.quantiles])
        # Separate quantile models can cross; sorting restores monotone quantiles.
        price = self._to_price(np.sort(raw, axis=1)) + self._level(table).to_numpy()[:, None]
        return pd.DataFrame(price, index=table.index, columns=self.quantiles)

    def predict(self, table: pd.DataFrame, apply_conformal: bool = True) -> pd.DataFrame:
        q = self.predict_quantiles(table)
        lo, mid, hi = (q[x].to_numpy() for x in config.QUANTILES)
        if apply_conformal and self.conformal_offsets:
            delta = table["horizon_days"].map(self.conformal_offsets).fillna(0.0).to_numpy()
            lo = np.minimum(lo - delta, mid)
            hi = np.maximum(hi + delta, mid)
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        out[list(PRICE_COLUMNS)] = np.column_stack([lo, mid, hi])
        return out

    def best_iterations(self) -> dict[str, int]:
        return {str(q): int(m.best_iteration_ or m.n_estimators) for q, m in self.models.items()}

    def metadata(self) -> dict:
        return {
            "quantiles": self.quantiles,
            "target_transform": self.target_transform,
            "level_columns": self.level_columns,
            "center": self.center,
            "scale": self.scale,
            "conformal_offsets": self.conformal_offsets,
        }
