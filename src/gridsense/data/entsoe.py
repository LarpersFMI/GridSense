import pandas as pd


def fetch_day_ahead_prices(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raise NotImplementedError


def fetch_load(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raise NotImplementedError


def fetch_generation(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raise NotImplementedError


def to_hourly(prices_15min: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to hourly mean/min/max; pre-Oct-2025 data is already hourly."""
    raise NotImplementedError
