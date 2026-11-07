import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, mean_pinball_loss


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


def slot_hit_rate(announced_slots: pd.DataFrame, prices: pd.DataFrame) -> float:
    raise NotImplementedError


def by_horizon(table: pd.DataFrame, metric_fn) -> pd.DataFrame:
    raise NotImplementedError
