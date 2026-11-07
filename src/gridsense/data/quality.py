import pandas as pd


def validate(df: pd.DataFrame, schema: dict[str, str], name: str) -> list[str]:
    """Return a list of problems (missing columns, gaps, duplicates, out-of-range values)."""
    raise NotImplementedError
