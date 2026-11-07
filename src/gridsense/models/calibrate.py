import numpy as np
import pandas as pd


def fit_isotonic(p_val: np.ndarray, y_val: np.ndarray):
    raise NotImplementedError


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
