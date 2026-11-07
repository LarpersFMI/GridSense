import pandas as pd


def top_features(model, X: pd.DataFrame, n: int = 3) -> pd.Series:
    """Top-n SHAP contributions per row, as a short string for the agent."""
    raise NotImplementedError
