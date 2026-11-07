"""Check a processed electricity dataset refresh without writing any outputs."""

import argparse
import json
from pathlib import Path

import pandas as pd

from gridsense import config, io
from gridsense.data.build import local_midnight, price_coverage
from gridsense.data.build_file_library import (
    EXPORTS,
    REGIONAL_KEY,
    SOURCE,
    complete_hours,
    file_library_load,
    unique_key,
    updated_by_next_issue,
)
from gridsense.data.build_regional import (
    BIDDING_ZONES,
    FORECAST_KEYS,
    LOAD_END,
    add_regional_features,
    forecast_grid,
)
from gridsense.data.entsoe import to_hourly
from gridsense.data.price_features import forecast_clock, utc_hours
from gridsense.data.weather import SOURCE_KEYS, validate_forecasts
from gridsense.schemas import FEATURE_PREFIX, PRICES_HOURLY


def hour_coverage(
    frame: pd.DataFrame, expected: pd.DatetimeIndex, name: str, *, require_complete: bool = False
) -> dict:
    if not frame.empty:
        unique_key(frame, ["ts_utc"], name)
    observed = pd.DatetimeIndex(utc_hours(frame["ts_utc"], name))
    missing = expected.difference(observed)
    unexpected = observed.difference(expected)
    if len(unexpected) or (require_complete and len(missing)):
        raise ValueError(
            f"{name}: {len(missing)} missing hours and {len(unexpected)} out-of-range hours"
        )
    return {
        "missing_hours": len(missing),
        "first_missing_utc": [ts.isoformat() for ts in missing[:5]],
    }


def require_same(
    actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str], reason: str
) -> None:
    unique_key(actual, keys, reason)
    try:
        pd.testing.assert_frame_equal(
            actual.sort_values(keys, ignore_index=True),
            expected.sort_values(keys, ignore_index=True),
            check_dtype=False,
            check_exact=True,
        )
    except AssertionError as error:
        raise ValueError(reason) from error


def check_market_refresh(directory: Path, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Verify staged or installed File Library outputs against source intervals and issue time."""

    def read(name: str, columns: list[str] | None = None) -> pd.DataFrame:
        return pd.read_parquet(directory / f"{name}.parquet", columns=columns)

    expected = pd.date_range(start, end, freq="h", inclusive="left", unit="ns")
    native = read("prices_native")
    unique_key(native, ["ts_utc"], "prices_native")
    hourly = read("prices_hourly")
    aggregated = to_hourly(native)
    if not native.ts_utc.between(start, end, inclusive="left").all():
        raise ValueError("prices_native contains out-of-range intervals")
    price_report = price_coverage(native, hourly, start, end)
    if price_report["missing_native_intervals"]:
        raise ValueError(
            f"prices_native: {price_report['missing_native_intervals']} missing intervals"
        )
    price_gaps = hour_coverage(hourly, expected, "prices_hourly", require_complete=True)
    require_same(
        hourly, aggregated, ["ts_utc"], "prices_hourly disagrees with the complete native intervals"
    )

    for name, (_, key) in EXPORTS.items():
        unique_key(read(f"{SOURCE}/{name}", key), key, f"{SOURCE}/{name}")

    regional_prices = read("regional_prices_hourly")
    regional_load = read("regional_load_hourly")
    unique_key(regional_prices, REGIONAL_KEY, "regional_prices_hourly")
    unique_key(regional_load, REGIONAL_KEY, "regional_load_hourly")
    if (
        set(regional_prices.country_code) != set(BIDDING_ZONES)
        or not regional_load.country_code.isin(BIDDING_ZONES).all()
    ):
        raise ValueError("Unexpected country coverage in regional market data")
    for country in BIDDING_ZONES:
        hour_coverage(
            regional_prices[regional_prices.country_code.eq(country)],
            expected,
            f"{country} prices",
            require_complete=True,
        )
    require_same(
        regional_prices.loc[regional_prices.country_code.eq("RO"), list(PRICES_HOURLY)],
        hourly,
        ["ts_utc"],
        "Regional Romanian prices disagree with prices_hourly",
    )
    load_gaps = {
        country: hour_coverage(
            regional_load[regional_load.country_code.eq(country)], expected, f"{country} load"
        )
        for country in BIDDING_ZONES
    }

    # Power Statistics load is kept as the historical baseline. Only File Library
    # observations carry an update timestamp that can be checked independently.
    from_library = regional_load.source.eq(SOURCE)
    if not regional_load.source.isin([SOURCE, "entsoe_power_statistics"]).all():
        raise ValueError("Unknown regional load provenance")
    if regional_load.loc[~from_library, "ts_utc"].ge(LOAD_END).any():
        raise ValueError("Power Statistics load extends beyond the pinned release")
    load_evidence = file_library_load(read(f"{SOURCE}/actual_load"))
    known = regional_load.loc[from_library, REGIONAL_KEY + ["load_actual_mw"]].merge(
        load_evidence[REGIONAL_KEY + ["load_actual_mw", "updated_at_utc"]],
        on=REGIONAL_KEY,
        how="left",
        validate="one_to_one",
        suffixes=("", "_source"),
    )
    if not known.load_actual_mw.eq(known.load_actual_mw_source).fillna(False).all():
        raise ValueError(
            "File Library load is missing complete source hours or disagrees with them"
        )
    late_load = known.loc[~updated_by_next_issue(known), REGIONAL_KEY]
    safe_load = regional_load.loc[
        ~pd.MultiIndex.from_frame(regional_load[REGIONAL_KEY]).isin(
            pd.MultiIndex.from_frame(late_load)
        )
    ]

    grid = read("grid_hourly")
    grid_gaps = hour_coverage(grid, expected, "grid_hourly")
    expected_grid = regional_load.loc[
        regional_load.country_code.eq("RO"), ["ts_utc", "load_actual_mw"]
    ].copy()
    expected_grid["load_actual_mw"] = expected_grid.load_actual_mw.where(
        expected_grid.ts_utc.isin(safe_load.loc[safe_load.country_code.eq("RO"), "ts_utc"])
    )
    generation = read(
        f"{SOURCE}/generation",
        ["production_type", "ts_utc", "resolution", "generation_mw", "updated_at_utc"],
    )
    excluded = {"load_actual_mw": len(late_load)}
    for fuel, value in (("Solar", "solar_actual_mw"), ("Wind Onshore", "wind_actual_mw")):
        hours = complete_hours(generation[generation.production_type.eq(fuel)], "generation_mw")
        available = updated_by_next_issue(hours)
        excluded[value] = int((~available).sum())
        expected_grid = expected_grid.merge(
            hours[["ts_utc"]].assign(**{value: hours.generation_mw.where(available)}),
            on="ts_utc",
            how="outer",
            validate="one_to_one",
        )
    require_same(
        grid,
        expected_grid,
        ["ts_utc"],
        "grid_hourly disagrees with the source data available by 10:00",
    )
    require_same(
        read("regional_market_features"),
        add_regional_features(forecast_grid(start, end), regional_prices, safe_load),
        list(FORECAST_KEYS),
        "regional_market_features disagrees with the issue-time source data",
    )
    return {
        "price_hourly_coverage": price_gaps,
        "missing_native_price_intervals": price_report["missing_native_intervals"],
        "regional_load_coverage": load_gaps,
        "grid_hourly_coverage": grid_gaps,
        "grid_missing_values_by_column": grid.drop(columns="ts_utc").isna().sum().to_dict(),
        "file_library_hours_excluded_by_cutoff": excluded,
        "legacy_load_timing": "Pinned Power Statistics baseline has no original publication timestamps.",
    }


def check_forecast_keys(table: pd.DataFrame, name: str) -> None:
    unique_key(table, list(FORECAST_KEYS), name)
    issue_day, _ = forecast_clock(table)
    target_day = (
        table.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    )
    if not target_day.sub(issue_day).dt.days.eq(table.horizon_days).all():
        raise ValueError(f"{name}: horizon does not match local issue and delivery dates")


def check_handoff(directory: Path) -> dict:
    """Check forecast contracts present in a completed dataset directory."""
    summary = {}
    expected_keys = None
    path = directory / "calendar.parquet"
    if path.is_file():
        calendar = pd.read_parquet(path)
        io.check_columns(calendar, "calendar")
        unique_key(calendar, ["ts_utc"], "calendar")
        hours = utc_hours(calendar.ts_utc, "calendar")
        start = hours.min()
        end = hours.max() + pd.Timedelta(hours=1)
        expected = pd.date_range(start, end, freq="h", inclusive="left", unit="ns")
        summary["calendar_coverage"] = hour_coverage(
            calendar, expected, "calendar", require_complete=True
        )
        expected_keys = forecast_grid(start, end)
        expected_keys = expected_keys[expected_keys.issue_ts.ge(start)]
    path = directory / "training_table.parquet"
    if path.is_file():
        table = pd.read_parquet(path)
        io.check_columns(table, "training_table")
        check_forecast_keys(table, "training_table")
        if expected_keys is not None:
            require_same(
                table[list(FORECAST_KEYS)],
                expected_keys,
                list(FORECAST_KEYS),
                "training_table has missing or unexpected calendar forecast keys",
            )
        expected_keys = table[list(FORECAST_KEYS)]
        if any(
            table[column].notna().any()
            for column in (f"{FEATURE_PREFIX}load_fc_min", f"{FEATURE_PREFIX}load_fc_max")
            if column in table
        ):
            raise ValueError(
                "training_table contains legacy week-ahead load features without as-of evidence"
            )
        summary["training_keys"] = len(table)
    path = directory / "weather_fc.parquet"
    if path.is_file():
        weather = pd.read_parquet(path)
        io.check_columns(weather, "weather_fc")
        unique_key(weather, SOURCE_KEYS, "weather_fc")
        validate_forecasts(weather)
        summary["weather_cutoff"] = (
            "Conservative archived-weather publication buffer checked."
            if "assumed_available_by_utc" in weather
            else "Unverified: archive availability timestamps missing."
        )
    for name, columns in {
        "load_fc_week_ahead_asof": [
            ("load_fc_min_mw", "load_fc_updated_at_utc"),
            ("load_fc_max_mw", "load_fc_updated_at_utc"),
        ],
        "renewable_generation_asof": [
            (f"{fuel}_daily_mw", f"{fuel}_updated_at_utc") for fuel in ("solar", "wind")
        ],
    }.items():
        path = directory / f"{name}.parquet"
        if not path.is_file():
            continue
        table = pd.read_parquet(path)
        check_forecast_keys(table, name)
        if expected_keys is not None:
            require_same(
                table[list(FORECAST_KEYS)],
                expected_keys,
                list(FORECAST_KEYS),
                f"{name} has missing or unexpected forecast keys",
            )
        for value, timestamp in columns:
            if not isinstance(table[timestamp].dtype, pd.DatetimeTZDtype):
                raise TypeError(f"{name}: {timestamp} must be timezone-aware")
            available = table[timestamp].le(table.issue_ts).fillna(False)
            if (table[value].notna() & ~available).any():
                raise ValueError(f"{name}: {value} lacks evidence by the 10:00 issue cutoff")
        summary[name] = len(table)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=config.PROCESSED_DIR)
    args = parser.parse_args()
    start = local_midnight(config.TRAIN_START.date())
    end = local_midnight(config.TEST_END.date() + pd.Timedelta(days=1))
    try:
        market = check_market_refresh(args.directory, start, end)
        handoff = check_handoff(args.directory)
    except (OSError, TypeError, ValueError, KeyError) as error:
        parser.exit(1, f"Dataset checks failed: {error}\n")
    print(json.dumps({"market": market, "handoff": handoff}, indent=2))


if __name__ == "__main__":
    main()
