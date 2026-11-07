"""Verify regional features against the ML table using the March 2025 synthetic-weather fixture."""

import argparse

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.data.check_weather_join import ISSUE_TS, OUTPUT_DIR, TARGET_DAY, synthetic_weather
from gridsense.data.price_features import delivery_lag_keys, forecast_clock
from gridsense.features.build import build_training_table

JOIN_KEYS = ["issue_ts", "target_ts_utc", "horizon_days"]


def join_regional_features(
    training: pd.DataFrame, regional: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    """Left join the ML table on its forecast key and report unmatched forecasts."""
    if regional.duplicated(JOIN_KEYS).any() or training.duplicated(JOIN_KEYS).any():
        raise ValueError("Forecast keys must be unique in both tables")
    feature_columns = [name for name in regional.columns if name.startswith("f_")]
    if not feature_columns:
        raise ValueError("The regional table has no f_ feature columns")
    if overlap := set(feature_columns) & set(training.columns):
        raise ValueError(f"Regional features already exist in the ML table: {sorted(overlap)}")
    merged = training.merge(
        regional[JOIN_KEYS + feature_columns],
        on=JOIN_KEYS,
        how="left",
        validate="one_to_one",
        indicator=True,
        sort=False,
    )
    missing = int(merged["_merge"].eq("left_only").sum())
    return merged.drop(columns="_merge"), missing


def calendar_fixture() -> pd.DataFrame:
    """Build a small synthetic calendar for the validation-day integration check."""
    end = pd.Timestamp(TARGET_DAY + pd.Timedelta(days=1), tz=config.LOCAL_TZ)
    start = pd.Timestamp(TARGET_DAY - pd.Timedelta(days=8), tz=config.LOCAL_TZ)
    local = pd.date_range(start, end, freq="h", inclusive="left")
    return pd.DataFrame(
        {
            "ts_utc": local.tz_convert("UTC").as_unit("ns"),
            "is_holiday": False,
            "is_bridge_day": False,
            "is_dst": [bool(ts.dst()) for ts in local],
            "day_hours": local.normalize().map(local.normalize().value_counts()).astype("int64"),
        }
    )


def verify_sample(prices: pd.DataFrame, grid: pd.DataFrame, regional: pd.DataFrame) -> pd.DataFrame:
    """Check the ML-P training entry point, real load, and regional joins on one DST day."""
    table = build_training_table(prices, grid, synthetic_weather(), calendar_fixture())
    sample = table.loc[(table["issue_ts"] == ISSUE_TS) & table["horizon_days"].eq(1)].copy()
    if len(sample) != 23 or sample["target_ts_utc"].nunique() != 23:
        raise ValueError("Expected 23 unique D+1 delivery hours on the spring DST day")
    if sample["y_price"].isna().any():
        raise ValueError("The sample has missing real price labels")
    joined, missing = join_regional_features(sample, regional)
    if missing:
        raise ValueError(f"Missing regional features for {missing} forecast keys")

    issue_days, target_hour = forecast_clock(joined)
    source_keys = delivery_lag_keys(issue_days, target_hour, 1)
    expected = grid.set_index("ts_utc")["load_actual_mw"].reindex(source_keys).to_numpy()
    actual = joined["f_load_ro_same_hour_d_minus_1"].to_numpy()
    if np.isnan(expected).any() or not np.allclose(actual, expected, equal_nan=False):
        raise ValueError("Regional Romanian load lag does not match real grid data")
    local_date = grid["ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.date
    day_before = ISSUE_TS.tz_convert(config.LOCAL_TZ).date() - pd.Timedelta(days=1)
    daily_load = grid.loc[local_date.eq(day_before), "load_actual_mw"]
    if len(daily_load) != 24 or not np.allclose(joined["f_load_mean_dm1"], daily_load.mean()):
        raise ValueError("ML daily Romanian load feature does not match the complete prior day")
    return joined


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real for the local real market tables")

    try:
        prices = io.read("prices_hourly")
        grid = io.read("grid_hourly")
        regional = pd.read_parquet(config.PROCESSED_DIR / "regional_market_features.parquet")
        joined = verify_sample(prices, grid, regional)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        joined.to_parquet(OUTPUT_DIR / "ml_regional_join.synthetic.parquet", index=False)
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(1, f"ML regional join failed: {exc}\n")
    print(f"ML regional join OK: {len(joined)} unique D+1 hours, real RO load and prices.")


if __name__ == "__main__":
    main()
