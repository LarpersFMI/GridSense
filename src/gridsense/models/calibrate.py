from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

# --- Probability calibration (ML-C) ---
# A calibrator maps the classifier's raw probability to one that matches observed frequencies.
# Both kinds are fitted on validation predictions and never decrease, so the order of hours is kept.


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


@dataclass
class PlattCalibrator:
    """Platt scaling: p_cal = sigmoid(a * logit(p) + b), a smooth S-curve with two parameters.

    Strictly increasing (a > 0 for any useful model), so every hour keeps its rank, and two
    parameters can't overfit the few hundred positives in validation.
    """

    a: float = 1.0
    b: float = 0.0

    def fit(self, p: np.ndarray, y: np.ndarray) -> "PlattCalibrator":
        lr = LogisticRegression(C=1e6).fit(_logit(p)[:, None], np.asarray(y, dtype=int))
        self.a, self.b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
        return self

    def predict(self, p: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-(self.a * _logit(p) + self.b)))


def fit_isotonic(p_val: np.ndarray, y_val: np.ndarray) -> IsotonicRegression:
    """Isotonic regression: the best-fitting non-decreasing step function.

    Very flexible, but with rare positives it merges thousands of distinct raw probabilities into a
    few dozen steps (ties), which costs ranking quality. Inputs outside the fitted range are clipped.
    """
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    return iso.fit(np.asarray(p_val, dtype=float), np.asarray(y_val, dtype=float))


def fit_platt(p_val: np.ndarray, y_val: np.ndarray) -> PlattCalibrator:
    return PlattCalibrator().fit(p_val, y_val)


CALIBRATORS = {"platt": fit_platt, "isotonic": fit_isotonic}


def fit_calibrator(p_val: np.ndarray, y_val: np.ndarray, method: str = "platt"):
    """Fitted calibrator with .predict(p) -> calibrated p; method is a key of CALIBRATORS."""
    return CALIBRATORS[method](p_val, y_val)


def cross_fit(
    p: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    method: str = "platt",
    fit_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Calibrated probabilities where each group is mapped by a calibrator fitted on the others.

    Scoring a calibrator on the rows it was fitted on looks better than it is. This gives honest
    calibrated validation scores; the model itself is still calibrated on all of validation.
    fit_mask limits which rows calibrators are fitted on (e.g. a conditional model that only
    applies to near-zero hours); every row is still mapped.
    """
    p, y, groups = np.asarray(p, dtype=float), np.asarray(y, dtype=float), np.asarray(groups)
    fit_mask = np.ones(len(p), dtype=bool) if fit_mask is None else np.asarray(fit_mask, dtype=bool)
    out = np.empty_like(p)
    for g in np.unique(groups):
        held = groups == g
        fit = ~held & fit_mask
        out[held] = fit_calibrator(p[fit], y[fit], method).predict(p[held])
    return out


def reliability_table(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Per probability bin: mean predicted probability, observed rate and row count.

    Perfectly calibrated: predicted == observed in every bin (the diagonal of a reliability plot).
    """
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    bins = np.minimum((p * n_bins).astype(int), n_bins - 1)
    df = pd.DataFrame({"bin": bins, "p": p, "y": y})
    return df.groupby("bin").agg(
        predicted=("p", "mean"), observed=("y", "mean"), rows=("y", "size")
    )


def plot_reliability(curves: dict[str, pd.DataFrame], path: Path, title: str = "") -> None:
    """Reliability plot of one or more reliability_table() results, saved as an image."""
    fig = Figure(figsize=(5, 5))
    ax = fig.subplots()
    ax.plot([0, 1], [0, 1], "--", color="grey", label="perfectly calibrated")
    for name, table in curves.items():
        ax.plot(table["predicted"], table["observed"], marker="o", label=name)
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="predicted probability", ylabel="observed frequency")
    ax.set_title(title)
    ax.legend(loc="upper left")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, bbox_inches="tight")


# --- Price intervals (ML-P) ---


def conformal_offsets(
    y: pd.Series, lo: pd.Series, hi: pd.Series, horizon: pd.Series, coverage: float
) -> dict[int, float]:
    """Conformalized quantile regression: per-horizon amount to widen (or narrow, if negative) [lo, hi]."""
    score = np.maximum(lo - y, y - hi)
    offsets = {}
    for h, s in score.groupby(horizon):
        n = len(s)
        level = min(1.0, np.ceil((n + 1) * coverage) / n)
        offsets[int(h)] = float(np.quantile(s, level, method="higher"))
    return offsets
