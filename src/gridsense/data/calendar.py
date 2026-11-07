"""Romanian calendar: one row per local hour with holidays, bridge days and DST."""

import argparse
from datetime import date

import holidays
import numpy as np
import pandas as pd

from gridsense import config, io


def calendar_for_hours(ts: pd.DatetimeIndex) -> pd.DataFrame:
    """Calendar rows for consecutive local (Europe/Bucharest) hours."""
    day = ts.tz_localize(None).normalize()
    years = range(day.year.min(), day.year.max() + 1)
    holiday_days = pd.DatetimeIndex(list(holidays.country_holidays("RO", years=years)))

    days = pd.date_range(day.min(), day.max(), freq="D")
    off = pd.Series(days.isin(holiday_days) | (days.day_of_week >= 5), index=days)
    bridge = days[(~off & off.shift(1, fill_value=False) & off.shift(-1, fill_value=False)).to_numpy()]

    hours_per_day = pd.Series(day).value_counts()
    return pd.DataFrame(
        {
            "ts_utc": ts.tz_convert("UTC").as_unit("ns"),
            "is_holiday": day.isin(holiday_days),
            "is_bridge_day": day.isin(bridge),
            "is_dst": np.array([t.dst() != pd.Timedelta(0) for t in ts]),
            "day_hours": pd.Series(day).map(hours_per_day).to_numpy(dtype="int64"),
        }
    )


def build_calendar(start: date, end: date) -> pd.DataFrame:
    """Every local hour of the days start..end inclusive."""
    first = pd.Timestamp(start, tz=config.LOCAL_TZ)
    last = pd.Timestamp(end, tz=config.LOCAL_TZ) + pd.Timedelta(hours=23)
    return calendar_for_hours(pd.date_range(first, last, freq="h"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=config.TRAIN_START.date())
    # Targets reach 7 days past the last issue date.
    default_end = (config.TEST_END + pd.Timedelta(days=max(config.HORIZONS_DAYS))).date()
    parser.add_argument("--end", type=date.fromisoformat, default=default_end)
    args = parser.parse_args(argv)
    calendar = build_calendar(args.start, args.end)
    io.write(calendar, "calendar")
    print(f"[{config.DATA_MODE}] calendar: {len(calendar):,} hours, {args.start}..{args.end}")


if __name__ == "__main__":
    main()
