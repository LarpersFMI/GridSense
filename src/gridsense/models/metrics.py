import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, mean_pinball_loss

from gridsense import config


def classification_report(y_true: np.ndarray, p: np.ndarray, k: int) -> dict[str, float]:
    """PR-AUC, precision@k, Brier."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(p, dtype=float)
    top_k = np.argsort(-p)[:k]
    return {
        "positives": int(y.sum()),
        "pr_auc": float(average_precision_score(y, p)) if y.any() else float("nan"),
        "precision_at_k": float(y[top_k].mean()) if k > 0 else float("nan"),
        "brier": float(brier_score_loss(y, p)),
    }


def quantile_report(y_true: np.ndarray, quantiles: dict[float, np.ndarray]) -> dict[str, float]:
    """Pinball loss per quantile and coverage of the outer interval."""
    y = np.asarray(y_true, dtype=float)
    out = {
        f"pinball_p{round(q * 100)}": float(mean_pinball_loss(y, pred, alpha=q))
        for q, pred in quantiles.items()
    }
    lo, hi = min(quantiles), max(quantiles)
    out["coverage"] = float(np.mean((y >= quantiles[lo]) & (y <= quantiles[hi])))
    out["nominal_coverage"] = hi - lo
    return out


def price_report(y_true: pd.Series, pred: pd.DataFrame) -> dict[str, float]:
    """Point, quantile and interval metrics for price forecasts (columns price_p10/p50/p90)."""
    y = np.asarray(y_true, dtype=float)
    quantiles = {q: pred[f"price_p{round(q * 100)}"].to_numpy() for q in config.QUANTILES}
    out = quantile_report(y, quantiles)
    err = y - pred["price_p50"].to_numpy()
    low = y <= config.NEAR_ZERO_THRESHOLD_EUR
    out |= {
        "n": len(y),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mean_pinball": float(np.mean([v for k, v in out.items() if k.startswith("pinball_")])),
        "width": float(np.mean(quantiles[max(quantiles)] - quantiles[min(quantiles)])),
        "mae_low_price": float(np.mean(np.abs(err[low]))) if low.any() else float("nan"),
    }
    return out


def slot_hit_rate(announced_slots: pd.DataFrame, prices: pd.DataFrame) -> float:
    raise NotImplementedError


def by_horizon(table: pd.DataFrame, metric_fn) -> pd.DataFrame:
    """metric_fn(sub_table) -> dict, for all rows and for each horizon_days."""
    rows = {"all": metric_fn(table)}
    rows |= {int(h): metric_fn(group) for h, group in table.groupby("horizon_days")}
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("horizon")
