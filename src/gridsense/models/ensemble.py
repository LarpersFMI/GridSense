"""Quantile average of LEAR and LightGBM, weight chosen on validation pinball loss. Owner: ML-P."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
import pandas as pd

from gridsense.models.base import PRICE_COLUMNS
from gridsense.models.metrics import price_report

Predict = Callable[[pd.DataFrame], pd.DataFrame]
WEIGHTS = np.round(np.linspace(0.0, 1.0, 11), 2)


@dataclass
class PriceEnsemble:
    name: ClassVar[str] = "ensemble"
    first: Predict
    second: Predict
    weight: float = 0.5  # on `first`
    val_pinball: dict[float, float] = field(default_factory=dict, init=False)

    @staticmethod
    def _blend(a: pd.DataFrame, b: pd.DataFrame, weight: float) -> pd.DataFrame:
        cols = list(PRICE_COLUMNS)
        mixed = weight * a[cols].fillna(b[cols]) + (1 - weight) * b[cols].fillna(a[cols])
        out = a.copy()
        out[cols] = np.sort(mixed.to_numpy(), axis=1)
        return out

    def fit(self, val: pd.DataFrame) -> "PriceEnsemble":
        """Pick the weight on val. One parameter, so the in-sample optimism is small."""
        a, b = self.first(val), self.second(val)
        for w in WEIGHTS:
            report = price_report(val["y_price"], self._blend(a, b, w))
            self.val_pinball[float(w)] = report["mean_pinball"]
        self.weight = min(self.val_pinball, key=self.val_pinball.get)
        return self

    def predict(self, table: pd.DataFrame) -> pd.DataFrame:
        return self._blend(self.first(table), self.second(table), self.weight)
