"""Training table: one row per (issue date D, horizon h, local hour of D+h).

Known at issue time (10:00 on D): prices for delivery days <= D (D's were published on D-1),
grid actuals for days <= D-1, and weather forecasts issued on D.
"""

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.schemas import FEATURE_PREFIX as F
from gridsense.splits import assign_split

MIDDAY_HOURS = range(11, 15)
EVENING_HOURS = range(18, 22)
FOURIER_ORDER = 3
WEATHER_VARS = {"ghi_wm2": "ghi", "cloud_cover_pct": "cloud", "wind100_ms": "wind100", "temp_c": "temp"}


def _local(ts_utc: pd.Series) -> pd.DataFrame:
    local = ts_utc.dt.tz_convert(config.LOCAL_TZ)
    return pd.DataFrame(
        {"date": local.dt.tz_localize(None).dt.normalize(), "hour": local.dt.hour}, index=ts_utc.index
    )


def _daily_price_features(prices: pd.DataFrame) -> pd.DataFrame:
    p = prices[["price_mean"]].join(_local(prices["ts_utc"]))
    by_day = p.groupby("date")["price_mean"]
    daily = pd.DataFrame(
        {
            "d_min": by_day.min(),
            "d_mean": by_day.mean(),
            "d_midday_min": p[p["hour"].isin(MIDDAY_HOURS)].groupby("date")["price_mean"].min(),
            "d_evening_max": p[p["hour"].isin(EVENING_HOURS)].groupby("date")["price_mean"].max(),
            "neg_hours": (p["price_mean"] <= config.CHEAP_THRESHOLD_EUR).groupby(p["date"]).sum(),
        }
    ).asfreq("D")  # missing days become NaN rows, so rolling windows are in calendar days
    daily["midday_min_7d"] = daily["d_midday_min"].rolling(7, min_periods=4).min()
    daily["midday_min_30d"] = daily["d_midday_min"].rolling(30, min_periods=15).min()
    daily["neg_hours_7d"] = daily["neg_hours"].rolling(7, min_periods=4).sum()
    daily["neg_hours_30d"] = daily["neg_hours"].rolling(30, min_periods=15).sum()
    daily["mean_30d"] = daily["d_mean"].rolling(30, min_periods=15).mean()
    return daily.drop(columns="neg_hours").add_prefix(F)


def _hourly_prices(prices: pd.DataFrame) -> pd.DataFrame:
    p = prices[["price_mean"]].join(_local(prices["ts_utc"]))
    # Mean over the duplicated hour when clocks go back.
    return p.groupby(["date", "hour"], as_index=False)["price_mean"].mean()


def _daily_grid_features(grid: pd.DataFrame) -> pd.DataFrame:
    g = grid.join(_local(grid["ts_utc"])).groupby("date")
    return pd.DataFrame(
        {
            "solar_max_dm1": g["solar_actual_mw"].max(),
            "wind_mean_dm1": g["wind_actual_mw"].mean(),
            "load_mean_dm1": g["load_actual_mw"].mean(),
        }
    ).asfreq("D").add_prefix(F)


def _weather_features(weather_fc: pd.DataFrame) -> pd.DataFrame:
    wide = weather_fc.pivot_table(
        index=["issue_date", "lead_days", "target_ts_utc"],
        columns="location",
        values=list(WEATHER_VARS),
        aggfunc="mean",
    )
    wide.columns = [f"{F}{WEATHER_VARS[var]}_{loc}" for var, loc in wide.columns]
    for short in ("ghi", "cloud", "wind100", "temp"):
        wide[f"{F}{short}_mean"] = wide.filter(regex=f"^{F}{short}_").mean(axis=1)
    return wide.reset_index().rename(columns={"lead_days": "horizon_days"})


def _calendar_features(rows: pd.DataFrame) -> pd.DataFrame:
    local = rows["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    doy = local.dt.day_of_year.to_numpy()
    feats = {
        f"{F}hour": rows["hour"],
        f"{F}weekday": local.dt.day_of_week,
        f"{F}is_weekend": (local.dt.day_of_week >= 5).astype("int8"),
        f"{F}is_holiday": rows["is_holiday"].astype("int8"),
        f"{F}is_bridge_day": rows["is_bridge_day"].astype("int8"),
        f"{F}is_dst": rows["is_dst"].astype("int8"),
        f"{F}month": local.dt.month,
        f"{F}horizon_days": rows["horizon_days"],
    }
    for k in range(1, FOURIER_ORDER + 1):
        feats[f"{F}doy_sin_{k}"] = np.sin(2 * np.pi * k * doy / 365.25)
        feats[f"{F}doy_cos_{k}"] = np.cos(2 * np.pi * k * doy / 365.25)
    return pd.DataFrame(feats, index=rows.index)


def build_training_table(
    prices: pd.DataFrame,
    grid: pd.DataFrame,
    weather_fc: pd.DataFrame,
    calendar: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (issue_date, target_ts, horizon); every feature must be known at issue time."""
    targets = calendar.rename(columns={"ts_utc": "target_ts_utc"})
    targets = targets.join(_local(targets["target_ts_utc"])).rename(columns={"date": "target_date"})
    rows = pd.concat(
        [
            targets.assign(horizon_days=h, issue_date=targets["target_date"] - pd.Timedelta(days=h))
            for h in config.HORIZONS_DAYS
        ],
        ignore_index=True,
    )
    rows = rows[rows["issue_date"] >= targets["target_date"].min()]
    rows["horizon_days"] = rows["horizon_days"].astype("int64")

    hourly = _hourly_prices(prices)
    rows = rows.merge(
        hourly.rename(columns={"date": "issue_date", "price_mean": f"{F}price_same_hour_d"}),
        on=["issue_date", "hour"],
        how="left",
    )
    rows["week_before_target"] = rows["target_date"] - pd.Timedelta(days=7)
    rows = rows.merge(
        hourly.rename(columns={"date": "week_before_target", "price_mean": f"{F}price_same_hour_target_m7"}),
        on=["week_before_target", "hour"],
        how="left",
    )
    rows = rows.merge(_daily_price_features(prices), left_on="issue_date", right_index=True, how="left")
    rows["day_before_issue"] = rows["issue_date"] - pd.Timedelta(days=1)
    rows = rows.merge(_daily_grid_features(grid), left_on="day_before_issue", right_index=True, how="left")
    rows = rows.merge(
        _weather_features(weather_fc), on=["issue_date", "horizon_days", "target_ts_utc"], how="left"
    )

    labels = prices[["ts_utc", "price_mean"]].rename(
        columns={"ts_utc": "target_ts_utc", "price_mean": "y_price"}
    )
    rows = rows.merge(labels, on="target_ts_utc", how="left")
    rows["y_near_zero"] = (rows["y_price"] <= config.NEAR_ZERO_THRESHOLD_EUR).astype("boolean")
    rows["y_cheap"] = (rows["y_price"] <= config.CHEAP_THRESHOLD_EUR).astype("boolean")
    rows.loc[rows["y_price"].isna(), ["y_near_zero", "y_cheap"]] = pd.NA

    rows["issue_ts"] = (
        (rows["issue_date"] + pd.Timedelta(hours=config.ISSUE_HOUR))
        .dt.tz_localize(config.LOCAL_TZ)
        .dt.tz_convert("UTC")
    )
    rows = pd.concat([rows, _calendar_features(rows)], axis=1)

    feature_cols = sorted(c for c in rows.columns if c.startswith(F))
    keys = ["issue_ts", "target_ts_utc", "horizon_days", "y_price", "y_near_zero", "y_cheap"]
    table = rows[keys + feature_cols].sort_values(["issue_ts", "horizon_days", "target_ts_utc"])
    return table.reset_index(drop=True)


def main() -> None:
    table = build_training_table(
        io.read("prices_hourly"), io.read("grid_hourly"), io.read("weather_fc"), io.read("calendar")
    )
    io.write(table, "training_table")

    n_features = sum(c.startswith(F) for c in table.columns)
    print(f"[{config.DATA_MODE}] training_table: {len(table):,} rows, {n_features} features")
    split = assign_split(table["target_ts_utc"]).fillna("unassigned")
    summary = table.groupby(split).agg(
        rows=("y_price", "size"),
        near_zero=("y_near_zero", "sum"),
        cheap=("y_cheap", "sum"),
    )
    print(summary.to_string())


if __name__ == "__main__":
    main()
