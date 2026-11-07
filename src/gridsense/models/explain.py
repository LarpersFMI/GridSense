"""Per-prediction explanations. Owner: SHAP top_features (ML-C), similar days (ML-P)."""

import lightgbm as lgb
import numpy as np
import pandas as pd

from gridsense.schemas import FEATURE_PREFIX


def shap_values(model: lgb.LGBMClassifier, X: pd.DataFrame) -> pd.DataFrame:
    """SHAP contribution of every feature to every row, in log-odds.

    Uses LightGBM's built-in TreeSHAP (exact for tree models). For each row,
    base value + sum of contributions = the model's raw score (log-odds of the event).
    """
    contrib = model.booster_.predict(X, pred_contrib=True)
    return pd.DataFrame(contrib[:, :-1], index=X.index, columns=X.columns)


def top_features(model: lgb.LGBMClassifier, X: pd.DataFrame, n: int = 3) -> pd.Series:
    """Top-n SHAP contributions per row, as a short string for the agent.

    E.g. "ghi_mean:+1.20; is_weekend:+0.45; cloud_mean:-0.30", largest effect first. "+" pushes
    the prediction toward a low price, "-" away from it. Values are log-odds, so compare them
    with each other rather than reading them as probabilities.
    """
    contrib = shap_values(model, X).to_numpy()
    names = np.array([c.removeprefix(FEATURE_PREFIX) for c in X.columns])
    n = min(n, contrib.shape[1])
    order = np.argsort(-np.abs(contrib), axis=1, kind="stable")[:, :n]
    values = np.take_along_axis(contrib, order, axis=1)
    text = [
        "; ".join(f"{name}:{v:+.2f}" for name, v in zip(names[o], vals, strict=True))
        for o, vals in zip(order, values, strict=True)
    ]
    return pd.Series(text, index=X.index, dtype="string")
