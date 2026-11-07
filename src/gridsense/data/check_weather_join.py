"""Check the four-city weather join against real prices on the March 2025 DST day."""

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.data.price_features import add_price_features, hourly_price_index, utc_hours
from gridsense.schemas import WEATHER_FC

TARGET_DAY = date(2025, 3, 30)
ISSUE_DAY = TARGET_DAY - timedelta(days=1)
ISSUE_TS = (
    (pd.Timestamp(ISSUE_DAY) + pd.Timedelta(hours=config.ISSUE_HOUR))
    .tz_localize(config.LOCAL_TZ)
    .tz_convert("UTC")
)
WEATHER_VALUES = ("ghi_wm2", "cloud_cover_pct", "wind100_ms", "temp_c")
OUTPUT_DIR = config.INTERIM_DIR / f"weather_join_{TARGET_DAY.isoformat()}"


def target_hours() -> pd.DatetimeIndex:
    start = pd.Timestamp(TARGET_DAY, tz=config.LOCAL_TZ)
    end = pd.Timestamp(TARGET_DAY + timedelta(days=1), tz=config.LOCAL_TZ)
    return pd.date_range(start, end, freq="h", inclusive="left").tz_convert("UTC").as_unit("ns")


def synthetic_weather() -> pd.DataFrame:
    """Generate deterministic test values with the weather_fc contract."""
    locations = tuple(config.WEATHER_POINTS)
    frame = pd.MultiIndex.from_product(
        [target_hours(), locations], names=["target_ts_utc", "location"]
    ).to_frame(index=False)
    local_hour = frame["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.hour
    city = frame["location"].map({name: i for i, name in enumerate(locations)})
    frame["issue_date"] = pd.Timestamp(ISSUE_DAY)
    frame["lead_days"] = 1
    frame["ghi_wm2"] = (600 - 100 * (local_hour - 13).abs()).clip(lower=0) * (1 - city / 10)
    frame["cloud_cover_pct"] = 20 + 10 * city
    frame["wind100_ms"] = 3 + city + local_hour / 24
    frame["temp_c"] = 7 + city + local_hour / 4
    return frame[list(WEATHER_FC)].astype(WEATHER_FC)


def join_sample(weather: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Validate full city-hour coverage for the agreed D+1 issue and attach one label per hour."""
    io.check_columns(weather, "weather_fc")
    hours = target_hours()
    locations = tuple(config.WEATHER_POINTS)
    utc = utc_hours(weather["target_ts_utc"], "weather_fc.target_ts_utc")
    selected = (
        weather["issue_date"].eq(pd.Timestamp(ISSUE_DAY))
        & weather["lead_days"].eq(1)
        & utc.isin(hours)
        & weather["location"].isin(locations)
    )
    sample = weather.loc[selected, ["location", *WEATHER_VALUES]].copy()
    sample["target_ts_utc"] = utc[selected]
    keys = ["target_ts_utc", "location"]
    if sample.duplicated(keys).any():
        raise ValueError("weather_fc has duplicate city-hour rows for the sample issue")
    if len(sample) != len(hours) * len(locations):
        raise ValueError(f"Expected {len(hours)} weather hours for each of {len(locations)} cities")
    sample = sample.astype({column: WEATHER_FC[column] for column in WEATHER_VALUES})
    if not np.isfinite(sample[list(WEATHER_VALUES)].to_numpy()).all():
        raise ValueError("Sample weather features must contain finite values")

    wide = sample.pivot(index="target_ts_utc", columns="location", values=list(WEATHER_VALUES))
    wide = wide.reindex(hours)
    wide.index.name = "target_ts_utc"
    wide.columns = [f"f_{variable}_{location}" for variable, location in wide.columns]
    wide["issue_ts"] = ISSUE_TS.as_unit("ns")
    wide["horizon_days"] = 1
    labels = hourly_price_index(prices).reindex(hours)
    if labels.isna().any():
        raise ValueError(f"Missing real prices for {labels.isna().sum()} sample delivery hours")

    result = add_price_features(wide.reset_index(), prices)
    result["y_price"] = labels.to_numpy()
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weather", type=Path, help="Check a supplied weather_fc Parquet file")
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real for the real price labels")

    try:
        weather = pd.read_parquet(args.weather) if args.weather else synthetic_weather()
        result = join_sample(weather, io.read("prices_hourly"))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Weather join failed: {exc}\n")

    if args.weather is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        weather.to_parquet(OUTPUT_DIR / "weather_fc.synthetic.parquet", index=False)
        result.to_parquet(OUTPUT_DIR / "price_weather_join.synthetic.parquet", index=False)
    print(f"Join OK: {len(result)} unique UTC hours, {len(config.WEATHER_POINTS)} weather cities.")


if __name__ == "__main__":
    main()
