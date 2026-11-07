"""Build Romanian day-ahead prices using the shared GridSense Parquet contract."""

import argparse
import json
import logging
from datetime import date

import pandas as pd

from gridsense import config, io
from gridsense.data.entsoe import QUARTER_HOUR_START, fetch_day_ahead_prices, to_hourly
from gridsense.data.price_snapshot import REVISION, fetch_snapshot_prices


def local_midnight(day: date) -> pd.Timestamp:
    return pd.Timestamp(day, tz=config.LOCAL_TZ).tz_convert("UTC").as_unit("ns")


def price_coverage(
    native: pd.DataFrame, hourly: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> dict:
    expected_hours = pd.date_range(start, end, freq="h", inclusive="left")
    expected_native = expected_hours[expected_hours < QUARTER_HOUR_START]
    if end > QUARTER_HOUR_START:
        quarter_hours = pd.date_range(
            max(start, QUARTER_HOUR_START), end, freq="15min", inclusive="left"
        )
        expected_native = expected_native.append(quarter_hours)

    missing_native = expected_native.difference(native["ts_utc"])
    missing_hours = expected_hours.difference(hourly["ts_utc"])
    return {
        "requested_start_utc": start.isoformat(),
        "requested_end_exclusive_utc": end.isoformat(),
        "first_native_start_utc": native["ts_utc"].iloc[0].isoformat(),
        "last_native_end_utc": native["interval_end_utc"].iloc[-1].isoformat(),
        "first_hour_utc": hourly["ts_utc"].iloc[0].isoformat() if len(hourly) else None,
        "last_hour_utc": hourly["ts_utc"].iloc[-1].isoformat() if len(hourly) else None,
        "expected_native_rows": len(expected_native),
        "native_rows": len(native),
        "native_rows_by_resolution": native["resolution"].value_counts().to_dict(),
        "missing_native_intervals": len(missing_native),
        "first_missing_native_intervals_utc": [ts.isoformat() for ts in missing_native[:10]],
        "native_coverage": len(native) / len(expected_native),
        "expected_hours": len(expected_hours),
        "hourly_rows": len(hourly),
        "missing_hours": len(missing_hours),
        "incomplete_hours": native["ts_utc"].dt.floor("h").nunique() - len(hourly),
        "hourly_coverage": len(hourly) / len(expected_hours),
        "negative_native_rows": int(native["price_eur_mwh"].lt(0).sum()),
        "negative_hours": int(hourly["price_mean"].lt(0).sum()),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("entsoe", "snapshot"), default="entsoe")
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        default=config.TRAIN_START.date(),
        help="First delivery date in Europe/Bucharest (inclusive)",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=config.TEST_END.date(),
        help="Last delivery date in Europe/Bucharest (inclusive)",
    )
    parser.add_argument(
        "--allow-gaps",
        action="store_true",
        help="Write validated observations and complete hours even if coverage has gaps",
    )
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Set GRIDSENSE_DATA=real to build real market data")
    if args.end < args.start:
        parser.error("--end must be on or after --start")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    start = local_midnight(args.start)
    end = local_midnight(args.end + pd.Timedelta(days=1))
    fetch = fetch_day_ahead_prices if args.source == "entsoe" else fetch_snapshot_prices
    try:
        native = fetch(start, end)
        hourly = to_hourly(native)
    except (TypeError, ValueError, OSError) as exc:
        parser.exit(1, f"Market data build failed: {exc}\n")

    summary = price_coverage(native, hourly, start, end)
    summary.update(
        source=native["source"].iloc[0],
        snapshot_revision=REVISION if args.source == "snapshot" else None,
        bidding_zone=config.BIDDING_ZONE,
        unit="EUR/MWh",
    )
    report = json.dumps(summary, indent=2, sort_keys=True)
    print(report, flush=True)
    if hourly.empty or (summary["missing_native_intervals"] and not args.allow_gaps):
        parser.exit(1, "Incomplete price coverage. See the report above. No outputs written.\n")

    io.write(hourly, "prices_hourly")
    native.to_parquet(config.PROCESSED_DIR / "prices_native.parquet", index=False)
    (config.PROCESSED_DIR / "prices_quality.json").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
