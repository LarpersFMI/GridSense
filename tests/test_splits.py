import pandas as pd

from gridsense import config
from gridsense.splits import assign_split


def test_assign_split_boundaries_and_gap():
    ts = pd.Series(
        pd.to_datetime(
            [
                "2024-06-01 10:00",
                "2025-06-01 10:00",
                "2025-12-01 10:00",
                "2026-04-01 10:00",
            ]
        ).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    )
    split = assign_split(ts)
    assert split[[0, 1, 3]].tolist() == ["train", "val", "test"]
    assert pd.isna(split[2])
