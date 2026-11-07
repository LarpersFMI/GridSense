import pandas as pd

from gridsense import config
from gridsense.schemas import TABLES


def check_columns(df: pd.DataFrame, name: str) -> None:
    missing = set(TABLES[name]) - set(df.columns)
    if missing:
        raise ValueError(f"{name}: missing columns {sorted(missing)}")


def read(name: str) -> pd.DataFrame:
    df = pd.read_parquet(config.PROCESSED_DIR / f"{name}.parquet")
    check_columns(df, name)
    return df


def write(df: pd.DataFrame, name: str) -> None:
    check_columns(df, name)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.PROCESSED_DIR / f"{name}.parquet", index=False)
