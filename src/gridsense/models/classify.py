"""Low-price classification: P(price <= 20) and P(price <= 0) per hour. Owner: ML classification.

The two probabilities are nested by construction (a chain):

    p_near_zero = P(price <= 20)
    p_cheap     = P(price <= 20) * P(price <= 0 | price <= 20)

Two separately trained and calibrated models gave p_cheap > p_near_zero on ~15% of validation
rows, which is impossible (every price <= 0 is also <= 20). A product of two probabilities can
never exceed either factor, so the chain can't contradict itself, raw or calibrated.
"""

from dataclasses import dataclass, field
from typing import ClassVar

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from gridsense import config
from gridsense.models.base import OUTPUT_COLUMNS, feature_columns, recency_weights
from gridsense.models.calibrate import PlattCalibrator, cross_fit, fit_calibrator

# Output probability column -> label it predicts (used by metrics, baselines and evaluation).
LABELS = {"p_near_zero": "y_near_zero", "p_cheap": "y_cheap"}

# The chain's steps: step name -> (label, label that must be true for a row to train/calibrate it).
NEAR_ZERO, CHEAP_GIVEN_NEAR_ZERO = "p_near_zero", "p_cheap_given_near_zero"
STEPS = {
    NEAR_ZERO: ("y_near_zero", None),
    CHEAP_GIVEN_NEAR_ZERO: ("y_cheap", "y_near_zero"),
}

DEFAULT_PARAMS = {
    # The only metric early stopping watches (= PR-AUC). Passing it as eval_metric instead would
    # add binary_logloss too, and early stopping halts on whichever metric stalls first.
    "metric": "average_precision",
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


def _rows(table: pd.DataFrame | None, condition: str | None) -> pd.DataFrame | None:
    if table is None or condition is None:
        return table
    return table[table[condition].astype(bool)]


@dataclass
class LowPriceClassifier:
    name: ClassVar[str] = "lgbm_classifier"
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    # Recency half-lives chosen with models.tune_classify on validation (2026-11-07): "<= 20" is
    # a stable multi-year pattern (long memory helps), "<= 0" only became common with the
    # 2024-25 solar build-out (older years mostly teach "never negative", so short memory helps).
    half_life_days: float | None = 730.0
    # Per chain step override of half_life_days.
    step_half_lives: dict[str, float | None] = field(
        default_factory=lambda: {CHEAP_GIVEN_NEAR_ZERO: 90.0}
    )
    early_stopping_rounds: int = 100
    # Calibrator fitted per chain step on val so probabilities match observed rates: "platt",
    # "isotonic" (see calibrate.py) or None for raw LightGBM probabilities.
    calibration: str | None = "platt"
    features: list[str] = field(default_factory=list, init=False)
    models: dict[str, lgb.LGBMClassifier] = field(default_factory=dict, init=False)
    calibrators: dict[str, PlattCalibrator | IsotonicRegression] = field(
        default_factory=dict, init=False
    )

    def fit(self, train: pd.DataFrame, val: pd.DataFrame | None = None) -> "LowPriceClassifier":
        self.features = feature_columns(train)
        for step, (label, condition) in STEPS.items():
            # The conditional step only learns from hours that were <= 20 €/MWh.
            tr, va = _rows(train, condition), _rows(val, condition)
            y = tr[label].astype(int)
            if y.nunique() < 2:
                raise ValueError(f"{label} has a single class in its train rows; can't fit {step}")
            model = lgb.LGBMClassifier(**self.params)
            fit_kwargs = {}
            if va is not None:
                fit_kwargs = {
                    "eval_X": (va[self.features],),
                    "eval_y": (va[label].astype(int),),
                    "callbacks": [lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
                }
            weights = recency_weights(tr, self.half_life(step))
            model.fit(tr[self.features], y, sample_weight=weights, **fit_kwargs)
            self.models[step] = model

            y_val = None if va is None else va[label].astype(int)
            if self.calibration and y_val is not None and y_val.nunique() == 2:
                raw = model.predict_proba(va[self.features])[:, 1]
                self.calibrators[step] = fit_calibrator(raw, y_val, self.calibration)
        return self

    def half_life(self, step: str) -> float | None:
        """Recency half-life (days) used for a chain step; None = no recency weighting."""
        return getattr(self, "step_half_lives", {}).get(step, self.half_life_days)

    def _check_chain(self) -> None:
        if CHEAP_GIVEN_NEAR_ZERO not in self.models:
            raise ValueError(
                "classifier artifact predates the nested chain; retrain with `make train TASK=classify`"
            )

    def step_probabilities(self, table: pd.DataFrame, apply_calibration: bool = True) -> dict:
        """Each chain step's probability for every row of `table`."""
        self._check_chain()
        calibrators = self.calibrators if apply_calibration else {}
        steps = {}
        for step, model in self.models.items():
            p = model.predict_proba(table[self.features])[:, 1]
            steps[step] = calibrators[step].predict(p) if step in calibrators else p
        return steps

    def _combine(self, table: pd.DataFrame, steps: dict) -> pd.DataFrame:
        out = pd.DataFrame(np.nan, index=table.index, columns=list(OUTPUT_COLUMNS))
        out["p_near_zero"] = steps[NEAR_ZERO]
        out["p_cheap"] = steps[NEAR_ZERO] * steps[CHEAP_GIVEN_NEAR_ZERO]
        return out

    def predict(self, table: pd.DataFrame, apply_calibration: bool = True) -> pd.DataFrame:
        return self._combine(table, self.step_probabilities(table, apply_calibration))

    def predict_cross_fitted(self, table: pd.DataFrame, groups: np.ndarray) -> pd.DataFrame:
        """Calibrated predictions where each group's calibrators were fitted on the other groups.

        For honest scores on the rows the calibrators were fitted on (validation). Needs the labels
        of `table`. Falls back to raw predictions when the model has no calibrators.
        """
        steps = self.step_probabilities(table, apply_calibration=False)
        for step, (label, condition) in STEPS.items():
            if step in self.calibrators:
                mask = None if condition is None else table[condition].astype(bool).to_numpy()
                y = table[label].astype(int).to_numpy()
                steps[step] = cross_fit(steps[step], y, groups, self.calibration, fit_mask=mask)
        return self._combine(table, steps)

    def explain_models(self, col: str) -> list[lgb.LGBMClassifier]:
        """The step models whose scores make up an output column (for SHAP)."""
        self._check_chain()
        if col == "p_near_zero":
            return [self.models[NEAR_ZERO]]
        return [self.models[NEAR_ZERO], self.models[CHEAP_GIVEN_NEAR_ZERO]]

    def metadata(self) -> dict:
        return {
            "structure": "chain: p_cheap = p_near_zero * P(cheap | near_zero)",
            "calibration": self.calibration,
            "calibrated": sorted(self.calibrators),
            "step_half_lives": {step: self.half_life(step) for step in STEPS},
        }

    def best_iterations(self) -> dict[str, int]:
        return {step: int(m.best_iteration_ or m.n_estimators) for step, m in self.models.items()}
