import pandas as pd


def seasonal_naive(table: pd.DataFrame) -> pd.Series:
    """Same hour, last week known at issue time."""
    raise NotImplementedError


def climatology(train: pd.DataFrame, table: pd.DataFrame) -> pd.Series:
    """P(cheap) by month x weekday x hour, fitted on train only."""
    raise NotImplementedError


def solar_rule(table: pd.DataFrame, irradiance_threshold: float) -> pd.Series:
    raise NotImplementedError


def lear(train: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Lasso-estimated autoregressive model, one Lasso per hour of day; strong D+1 baseline."""
    raise NotImplementedError
