"""Build exact-hour day-ahead price features for an existing forecast grid."""

import numpy as np
import pandas as pd

from gridsense import config, io

HISTORY_DAYS = 7
MIDDAY_START = 11
MIDDAY_END = 15


def utc_hours(timestamps: pd.Series, name: str) -> pd.Series:
    """Normalize timezone-aware interval starts and reject invalid or off-grid hours."""
    if not isinstance(timestamps.dtype, pd.DatetimeTZDtype) or timestamps.isna().any():
        raise ValueError(f"{name} must contain valid timezone-aware timestamps")
    utc = timestamps.dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
    if utc.ne(utc.dt.floor("h")).any():
        raise ValueError(f"{name} must align to whole UTC hours")
    return utc


def hourly_price_index(prices: pd.DataFrame) -> pd.Series:
    io.check_columns(prices, "prices_hourly")
    utc = utc_hours(prices["ts_utc"], "prices_hourly.ts_utc")
    if utc.duplicated().any():
        raise ValueError("prices_hourly has duplicate delivery hours")
    values = pd.to_numeric(prices["price_mean"], errors="raise").astype("float64")
    if not np.isfinite(values).all():
        raise ValueError("prices_hourly.price_mean must contain finite prices")
    return pd.Series(values.to_numpy(), index=pd.DatetimeIndex(utc), name="price_mean")


def _daily_stats(prices: pd.Series, issue_days: pd.Series) -> pd.DataFrame:
    hours = pd.DatetimeIndex([], tz=config.LOCAL_TZ)
    if not issue_days.empty:
        first = issue_days.min() - pd.Timedelta(days=HISTORY_DAYS)
        end = issue_days.max() + pd.Timedelta(days=1)
        hours = pd.date_range(
            first.tz_localize(config.LOCAL_TZ),
            end.tz_localize(config.LOCAL_TZ),
            freq="h",
            inclusive="left",
        )
    values = prices.reindex(hours.tz_convert("UTC"))
    days = hours.tz_localize(None).normalize()
    midday = (hours.hour >= MIDDAY_START) & (hours.hour < MIDDAY_END)
    daily = values.groupby(days)
    midday_daily = values[midday].groupby(days[midday])

    complete_midday = midday_daily.count().eq(midday_daily.size())
    negative = values.lt(0).astype(float).where(values.notna())
    daily_counts = pd.DataFrame(
        {
            "observed": daily.count(),
            "expected": daily.size(),
            "negative": negative.groupby(days).sum(min_count=1),
            "midday_observed": midday_daily.count(),
            "midday_expected": midday_daily.size(),
        }
    )
    # Shift on a complete calendar grid. Day D contributes only to the same-day features.
    totals = daily_counts.shift(1).rolling(HISTORY_DAYS, min_periods=1).sum()
    return pd.DataFrame(
        {
            "f_price_midday_mean_d": midday_daily.mean().where(complete_midday),
            "f_price_midday_min_d": midday_daily.min().where(complete_midday),
            "f_price_midday_min_7d": midday_daily.min()
            .shift(1)
            .rolling(HISTORY_DAYS, min_periods=1)
            .min(),
            "f_negative_price_hours_7d": totals["negative"],
            "f_price_coverage_7d": totals["observed"] / totals["expected"],
            "f_price_midday_coverage_7d": totals["midday_observed"] / totals["midday_expected"],
        }
    )


def add_price_features(rows: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Add market features to rows keyed by issue_ts and target_ts_utc.

    At 10:00 local, day D's day-ahead auction has already cleared under the repo's
    availability policy. The historical price snapshot does not establish revision vintages.
    """
    price_index = hourly_price_index(prices)
    issue = utc_hours(rows["issue_ts"], "issue_ts").dt.tz_convert(config.LOCAL_TZ)
    target = utc_hours(rows["target_ts_utc"], "target_ts_utc").dt.tz_convert(config.LOCAL_TZ)
    issue_days = issue.dt.tz_localize(None).dt.normalize()
    target_days = target.dt.tz_localize(None).dt.normalize()
    lead = (target_days - issue_days).dt.days
    if issue.dt.hour.ne(config.ISSUE_HOUR).any() or not lead.isin(config.HORIZONS_DAYS).all():
        raise ValueError("Expected 10:00 Romanian issues and a configured future delivery day")

    result = rows.copy()
    target_hour = pd.to_timedelta(target.dt.hour, unit="h")
    for days_back, column in ((0, "f_price_same_hour_d"), (6, "f_price_same_hour_d_minus_6")):
        local_clock = issue_days + target_hour - pd.Timedelta(days=days_back)
        # A missing or repeated local hour cannot identify a unique delivery interval.
        keys = local_clock.dt.tz_localize(
            config.LOCAL_TZ,
            ambiguous="NaT",
            nonexistent="NaT",
        ).dt.tz_convert("UTC")
        result[column] = price_index.reindex(pd.DatetimeIndex(keys)).to_numpy()

    stats = _daily_stats(price_index, issue_days).reindex(issue_days)
    for column in stats:
        result[column] = stats[column].to_numpy()
    return result
