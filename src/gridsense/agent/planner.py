import pandas as pd


def candidate_slots(predictions: pd.DataFrame, min_hours: int = 2, max_hours: int = 6) -> pd.DataFrame:
    """Contiguous blocks between 09:00 and 18:00 local time."""
    raise NotImplementedError


def plan(slots: pd.DataFrame, budget_used_hours: int) -> pd.DataFrame:
    raise NotImplementedError


def reconcile_with_auction(plan: pd.DataFrame, cleared_prices: pd.DataFrame) -> pd.DataFrame:
    """Confirm or cancel planned D+1 slots once day-ahead prices are published."""
    raise NotImplementedError
