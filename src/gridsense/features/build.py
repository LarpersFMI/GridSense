import pandas as pd


def build_training_table(
    prices: pd.DataFrame,
    grid: pd.DataFrame,
    weather_fc: pd.DataFrame,
    calendar: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (issue_date, target_ts, horizon); every feature must be known at issue time."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
