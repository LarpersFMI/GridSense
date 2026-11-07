"""Per-prediction explanations. Owner: SHAP top_features (ML-C), similar days (ML-P)."""

import lightgbm as lgb
import numpy as np
import pandas as pd

from gridsense.schemas import FEATURE_PREFIX

Models = lgb.LGBMClassifier | list[lgb.LGBMClassifier]


def shap_values(models: Models, X: pd.DataFrame) -> pd.DataFrame:
    """SHAP contribution of every feature to every row, in log-odds.

    Uses LightGBM's built-in TreeSHAP (exact for tree models). For one model, per row,
    base value + sum of contributions = the model's raw score (log-odds of the event).
    For a list (the classifier's chain, see LowPriceClassifier.explain_models), contributions
    are summed: p_cheap = p_near_zero * P(cheap | near_zero), so log p_cheap is the sum of the
    two log-probabilities, which log-odds approximate well for the small probabilities involved.
    """
    models = models if isinstance(models, list) else [models]
    contrib = sum(m.booster_.predict(X, pred_contrib=True)[:, :-1] for m in models)
    return pd.DataFrame(contrib, index=X.index, columns=X.columns)


def top_features(models: Models, X: pd.DataFrame, n: int = 3) -> pd.Series:
    """Top-n SHAP contributions per row, as a short string for the agent.

    E.g. "ghi_mean:+1.20; is_weekend:+0.45; cloud_mean:-0.30", largest effect first. "+" pushes
    the prediction toward a low price, "-" away from it. Values are log-odds, so compare them
    with each other rather than reading them as probabilities.
    """
    contrib = shap_values(models, X).to_numpy()
    names = np.array([c.removeprefix(FEATURE_PREFIX) for c in X.columns])
    n = min(n, contrib.shape[1])
    order = np.argsort(-np.abs(contrib), axis=1, kind="stable")[:, :n]
    values = np.take_along_axis(contrib, order, axis=1)
    text = [
        "; ".join(f"{name}:{v:+.2f}" for name, v in zip(names[o], vals, strict=True))
        for o, vals in zip(order, values, strict=True)
    ]
    return pd.Series(text, index=X.index, dtype="string")
