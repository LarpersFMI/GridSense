import pandas as pd

from gridsense import config

SPLITS = {
    "train": (config.TRAIN_START, config.TRAIN_END),
    "val": (config.VAL_START, config.VAL_END),
    "test": (config.TEST_START, config.TEST_END),
}


def assign_split(target_ts_utc: pd.Series) -> pd.Series:
    """Split by target time; rows outside every split (e.g. 2025-10 to 2026-02) are NaN."""
    out = pd.Series(None, index=target_ts_utc.index, dtype="object")
    for name, (start, end) in SPLITS.items():
        out[(target_ts_utc >= start) & (target_ts_utc <= end)] = name
    return out
