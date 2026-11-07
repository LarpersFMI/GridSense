"""Training table: one row per (issue date D, horizon h, local hour of D+h).

Known at issue time (10:00 on D): prices for delivery days <= D (D's were published on D-1),
grid actuals for days <= D-1, and weather forecasts issued on D.
"""

import argparse

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.schemas import FEATURE_PREFIX as F
from gridsense.splits import assign_split

MIDDAY_HOURS = range(11, 15)
EVENING_HOURS = range(18, 22)
FOURIER_ORDER = 3
# Archived forecast fields only. weather_hourly is observed weather and would leak target-hour truth.
WEATHER_VARS = {"ghi_wm2": "ghi", "cloud_cover_pct": "cloud", "wind100_ms": "wind100", "temp_c": "temp"}
# Optional archived forecast fields (make weather --extra); direction enters as a unit vector.
EXTRA_WEATHER_VARS = {"humidity_pct": "humidity", "precip_mm": "precip", "pressure_hpa": "pressure",
                      "wind10_ms": "wind10", "winddir_sin": "winddir_sin", "winddir_cos": "winddir_cos"}
# Week-ahead load forecasts appear on Thursday around 10:00-12:00 for the week starting the
# following Monday (measured on 2026 data). Saturday's issue is the first that safely has them.
LOAD_FC_KNOWN_DAYS_BEFORE_MONDAY = 2


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


def _same_hour_history(hourly: pd.DataFrame) -> pd.DataFrame:
    """Per local hour: day D-1 and the 7 days ending on D, keyed by (issue_date, hour)."""
    wide = hourly.pivot(index="date", columns="hour", values="price_mean").asfreq("D")
    week = wide.rolling(7, min_periods=4)
    parts = {
        f"{F}price_same_hour_dm1": wide.shift(1),
        f"{F}price_same_hour_mean_7d": week.mean(),
        f"{F}price_same_hour_min_7d": week.min(),
        f"{F}price_same_hour_max_7d": week.max(),
    }
    long = pd.concat({name: df.stack() for name, df in parts.items()}, axis=1)
    return long.rename_axis(["issue_date", "hour"]).reset_index()


def _daily_grid_features(grid: pd.DataFrame) -> pd.DataFrame:
    g = grid.join(_local(grid["ts_utc"])).groupby("date")
    return pd.DataFrame(
        {
            "solar_max_dm1": g["solar_actual_mw"].max(),
            "wind_mean_dm1": g["wind_actual_mw"].mean(),
            "load_mean_dm1": g["load_actual_mw"].mean(),
        }
    ).asfreq("D").add_prefix(F)


def _weather_features(weather_fc: pd.DataFrame, extra: bool = False) -> pd.DataFrame:
    io.check_columns(weather_fc, "weather_fc")
    if not weather_fc["lead_days"].isin(config.HORIZONS_DAYS).all():
        raise ValueError("Weather must contain real D+1…D+7 forecast leads, not observed weather")
    if "assumed_available_by_utc" in weather_fc:
        # Real archived inputs carry provenance; reject cutoff/key violations before joining.
        from gridsense.data.weather import validate_forecasts

        validate_forecasts(weather_fc)
    variables = dict(WEATHER_VARS)
    if extra:
        if "wind_dir_deg" not in weather_fc:
            raise ValueError("weather_fc has no extra variables; run `make weather EXTRA=1` first")
        radians = np.deg2rad(weather_fc["wind_dir_deg"])
        weather_fc = weather_fc.assign(winddir_sin=np.sin(radians), winddir_cos=np.cos(radians))
        variables |= EXTRA_WEATHER_VARS
    wide = weather_fc.pivot_table(
        index=["issue_date", "lead_days", "target_ts_utc"],
        columns="location",
        values=list(variables),
        aggfunc="mean",
    )
    wide.columns = [f"{F}{variables[var]}_{loc}" for var, loc in wide.columns]
    for short in variables.values():
        wide[f"{F}{short}_mean"] = wide.filter(regex=f"^{F}{short}_(?!mean$)").mean(axis=1)
    return wide.reset_index().rename(columns={"lead_days": "horizon_days"})


def _week_ahead_load_features(rows: pd.DataFrame, load_fc: pd.DataFrame) -> pd.DataFrame:
    """Target-day load forecast, NaN where it was not yet published at issue time."""
    fc = load_fc.set_index("target_date")[["load_fc_min_mw", "load_fc_max_mw"]]
    joined = fc.reindex(rows["target_date"]).set_axis(rows.index)
    monday = rows["target_date"] - pd.to_timedelta(rows["target_date"].dt.day_of_week, unit="D")
    known = rows["issue_date"] >= monday - pd.Timedelta(days=LOAD_FC_KNOWN_DAYS_BEFORE_MONDAY)
    return pd.DataFrame(
        {
            f"{F}load_fc_min": joined["load_fc_min_mw"].where(known),
            f"{F}load_fc_max": joined["load_fc_max_mw"].where(known),
        },
        index=rows.index,
    )


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
    grid: pd.DataFrame | None,
    weather_fc: pd.DataFrame | None,
    calendar: pd.DataFrame,
    load_fc_week_ahead: pd.DataFrame | None = None,
    weather_extra: bool = False,
) -> pd.DataFrame:
    """One row per (issue_date, target_ts, horizon); every feature must be known at issue time.

    Grid, weather and load forecast features are skipped when their table is None.
    """
    if "country" in calendar and not calendar["country"].isin(["Romania", "RO"]).all():
        raise ValueError("The ML target calendar must be Romanian; keep country calendars separate")
    if calendar["ts_utc"].duplicated().any():
        raise ValueError("The ML target calendar must have one row per UTC hour")
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
    rows = rows.merge(_same_hour_history(hourly), on=["issue_date", "hour"], how="left")
    rows["week_before_target"] = rows["target_date"] - pd.Timedelta(days=7)
    rows = rows.merge(
        hourly.rename(columns={"date": "week_before_target", "price_mean": f"{F}price_same_hour_target_m7"}),
        on=["week_before_target", "hour"],
        how="left",
    )
    rows = rows.merge(_daily_price_features(prices), left_on="issue_date", right_index=True, how="left")
    rows["day_before_issue"] = rows["issue_date"] - pd.Timedelta(days=1)
    if grid is not None:
        rows = rows.merge(
            _daily_grid_features(grid), left_on="day_before_issue", right_index=True, how="left"
        )
    if weather_fc is not None:
        rows = rows.merge(
            _weather_features(weather_fc, extra=weather_extra),
            on=["issue_date", "horizon_days", "target_ts_utc"],
            how="left",
        )
    if load_fc_week_ahead is not None:
        rows = rows.join(_week_ahead_load_features(rows, load_fc_week_ahead))

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
    quality_cols = []
    if weather_fc is not None:
        weather_prefixes = tuple(f"{F}{short}_" for short in WEATHER_VARS.values())
        weather_columns = [c for c in feature_cols if c.startswith(weather_prefixes)]
        complete = rows[weather_columns].notna().all(axis=1) if weather_columns else False
        # predict.build_predictions already passes this optional column to the agent. Missing
        # archive dates/horizons must not silently be presented as good-quality forecasts.
        rows["data_quality"] = np.where(complete, "ok", "missing_weather")
        quality_cols = ["data_quality"]
    table = rows[keys + feature_cols + quality_cols].sort_values(["issue_ts", "horizon_days", "target_ts_utc"])
    return table.reset_index(drop=True)


def _read_optional(name: str) -> pd.DataFrame | None:
    if (config.PROCESSED_DIR / f"{name}.parquet").is_file():
        return io.read(name)
    print(f"[{config.DATA_MODE}] no {name} table; building without its features")
    return None


def drop_untrainable(table: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """A model can't learn a feature with no training values; it would only switch on at refit/test."""
    train = assign_split(table["target_ts_utc"]).eq("train")
    empty = [c for c in table if c.startswith(F) and table.loc[train, c].isna().all()]
    return table.drop(columns=empty), empty


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regional", action="store_true",
                        help="Opt in to verified HU/BG market features; keep missing inputs flagged")
    parser.add_argument("--week-ahead", action="store_true",
                        help="Opt in to week-ahead load min/max; historical publication vintages are unverified")
    parser.add_argument("--weather-extra", action="store_true",
                        help="Opt in to humidity, precipitation, pressure and 10 m wind forecast features")
    parser.add_argument("--forecast-engineered", action="store_true",
                        help="Opt in to archived-forecast physical features and issue-time price memory")
    args = parser.parse_args(argv)
    if args.regional and config.DATA_MODE != "real":
        parser.error("Regional market inputs are real-only; do not mix them into fake mode")
    table = build_training_table(
        io.read("prices_hourly"),
        _read_optional("grid_hourly"),
        _read_optional("weather_fc"),
        io.read("calendar"),
        _read_optional("load_fc_week_ahead") if args.week_ahead else None,
        weather_extra=args.weather_extra,
    )
    if args.forecast_engineered:
        from gridsense.features.forecast_engineering import join_engineered_features

        table = join_engineered_features(table, io.read("weather_fc"), io.read("prices_hourly"))
    split = assign_split(table["target_ts_utc"]).fillna("unassigned")
    table, empty = drop_untrainable(table)
    if empty:
        print(f"[{config.DATA_MODE}] dropped features with no training values: {empty}")
    if args.regional:
        from gridsense.features.regional import join_regional_features, read_regional_table

        regional, _ = read_regional_table()
        table, missing = join_regional_features(table, regional)
        print(f"[{config.DATA_MODE}] regional join: {missing:,} unmatched forecast keys (retained)")
    io.write(table, "training_table")

    n_features = sum(c.startswith(F) for c in table.columns)
    print(f"[{config.DATA_MODE}] training_table: {len(table):,} rows, {n_features} features")
    summary = table.groupby(split).agg(
        rows=("y_price", "size"),
        near_zero=("y_near_zero", "sum"),
        cheap=("y_cheap", "sum"),
    )
    print(summary.to_string())


if __name__ == "__main__":
    main()
