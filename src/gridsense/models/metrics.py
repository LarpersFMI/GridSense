import numpy as np
import pandas as pd


def classification_report(y_true: np.ndarray, p: np.ndarray, k: int) -> dict[str, float]:
    """PR-AUC, precision@k, Brier."""
    raise NotImplementedError


def quantile_report(y_true: np.ndarray, quantiles: dict[float, np.ndarray]) -> dict[str, float]:
    """Pinball loss per quantile and P10-P90 coverage."""
    raise NotImplementedError


def slot_hit_rate(announced_slots: pd.DataFrame, prices: pd.DataFrame) -> float:
    raise NotImplementedError


def by_horizon(table: pd.DataFrame, metric_fn) -> pd.DataFrame:
    raise NotImplementedError
