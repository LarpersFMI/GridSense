"""Build local RO/HU/BG market tables and issue-relative features without weather."""

import argparse
import json
import logging
from hashlib import file_digest
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from gridsense import config
from gridsense.data.build import price_coverage
from gridsense.data.entsoe import LOGGER, download, to_hourly
from gridsense.data.price_features import (
    delivery_lag_keys,
    forecast_clock,
    hourly_price_index,
    utc_hours,
)
from gridsense.data.price_snapshot import (
    BIDDING_ZONES,
    REVISION,
    SNAPSHOT_END,
    fetch_snapshot_prices,
)
from gridsense.schemas import TRAINING_TABLE

POWER_STATS_URL = "https://www.entsoe.eu/publications/data/power-stats"
LOAD_FILE_SHA256 = {
    2023: "96525a65332ab6bcb180f1e435eedd32941909beabe2cf2b44baac9650436528",
    2024: "adcfe02c32f51babdb4ecc0a56391b1ecf9acb80c65aa974d2e543fd528434b7",
    2025: "cb18e827305823d5a773755ea4b066e4758205674a58ceb01367f22a8216a36a",
    2026: "e449af0b6c615b473c2e42aa33e7c4248c4bd8672a28a75e35383aee3a190b04",
}
LOAD_START = pd.Timestamp("2023-01-01", tz="UTC")
LOAD_END = pd.Timestamp("2026-07-01", tz="UTC")  # Pinned 2026 release contains Q1 and Q2.
FORECAST_KEYS = {k: TRAINING_TABLE[k] for k in ("issue_ts", "target_ts_utc", "horizon_days")}


def sha256_file(path: Path) -> str:
    with path.open("rb") as fh:
        return file_digest(fh, "sha256").hexdigest()


def fetch_power_stats_load() -> pd.DataFrame:
    """Read pinned official hourly load files, retaining complete country-hour observations."""
    raw_dir = config.RAW_DIR / "entsoe_load" / "power_stats"
    frames = []
    with requests.Session() as session:
        for year, expected_sha in LOAD_FILE_SHA256.items():
            path = raw_dir / f"monthly_hourly_load_values_{year}.csv"
            if not path.is_file():
                LOGGER.info("Downloading ENTSO-E Power Statistics load for %s", year)
                download(session, f"{POWER_STATS_URL}/{year}/{path.name}", path)
            if sha256_file(path) != expected_sha:
                raise ValueError(
                    f"Checksum mismatch for {path}. Use the pinned release from a teammate's cache "
                    "or review and update the release pin."
                )

            with path.open(encoding="utf-8-sig") as fh:
                sep = "\t" if "\t" in fh.readline() else ","
            fields = ["DateUTC", "CountryCode", "Cov_ratio", "Value"]
            data = pd.read_csv(path, sep=sep, encoding="utf-8-sig", usecols=fields)
            selected = data["CountryCode"].isin(BIDDING_ZONES) & data["Cov_ratio"].eq(100)
            frame = data.loc[selected, ["DateUTC", "CountryCode", "Value"]].rename(
                columns={
                    "DateUTC": "ts_utc",
                    "CountryCode": "country_code",
                    "Value": "load_actual_mw",
                }
            )
            frame["ts_utc"] = pd.to_datetime(frame["ts_utc"], format="%d-%m-%Y %H:%M", utc=True)
            if not frame["ts_utc"].dt.year.eq(year).all():
                raise ValueError(f"{path.name} includes hours outside {year}")
            frames.append(frame)

    load = pd.concat(frames, ignore_index=True)
    load["ts_utc"] = utc_hours(load["ts_utc"], "regional_load_hourly.ts_utc")
    if not load["ts_utc"].between(LOAD_START, LOAD_END, inclusive="left").all():
        raise ValueError("Load observations outside the pinned release window")
    if load.duplicated(["country_code", "ts_utc"]).any():
        raise ValueError("Duplicate country-hour in ENTSO-E Power Statistics load")
    values = pd.to_numeric(load["load_actual_mw"]).astype("float64")
    if not (np.isfinite(values) & values.ge(0)).all():
        raise ValueError("Hourly load must be a finite, nonnegative value")
    if set(load["country_code"]) != set(BIDDING_ZONES):
        raise ValueError("The load releases must include RO, HU and BG")

    load["load_actual_mw"] = values
    load["bidding_zone"] = load["country_code"].map(BIDDING_ZONES)
    load["source"] = "entsoe_power_statistics"
    columns = ["country_code", "bidding_zone", "ts_utc", "load_actual_mw", "source"]
    return (
        load[columns]
        .astype(
            {
                "country_code": "string",
                "bidding_zone": "string",
                "source": "string",
            }
        )
        .sort_values(["country_code", "ts_utc"], ignore_index=True)
    )


def forecast_grid(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    local_days = hours.tz_convert(config.LOCAL_TZ).tz_localize(None).normalize()
    frames = []
    for horizon in config.HORIZONS_DAYS:
        issue_clock = (
            local_days - pd.Timedelta(days=horizon) + pd.Timedelta(hours=config.ISSUE_HOUR)
        )
        issue_ts = issue_clock.tz_localize(config.LOCAL_TZ).tz_convert("UTC")
        frames.append(
            pd.DataFrame(
                {
                    "issue_ts": issue_ts,
                    "target_ts_utc": hours,
                    "horizon_days": horizon,
                }
            )
        )
    return (
        pd.concat(frames, ignore_index=True)
        .astype(FORECAST_KEYS)
        .sort_values(
            ["issue_ts", "target_ts_utc"],
            ignore_index=True,
        )
    )


def add_regional_features(
    rows: pd.DataFrame, prices: pd.DataFrame, load: pd.DataFrame
) -> pd.DataFrame:
    """Look up cleared prices on D/D−6 and measured load on D−1, keyed by exact UTC hour."""
    issue_days, target_hour = forecast_clock(rows)
    result = rows.copy()
    price_series = {
        country: hourly_price_index(prices.loc[prices["country_code"].eq(country)])
        for country in BIDDING_ZONES
    }
    for days_back, suffix in ((0, "d"), (6, "d_minus_6")):
        keys = delivery_lag_keys(issue_days, target_hour, days_back)
        ro = price_series["RO"].reindex(keys).to_numpy()
        for country in ("HU", "BG"):
            neighbor = price_series[country].reindex(keys).to_numpy()
            code = country.lower()
            result[f"f_price_{code}_same_hour_{suffix}"] = neighbor
            result[f"f_price_spread_ro_{code}_{suffix}"] = ro - neighbor

    keys = delivery_lag_keys(issue_days, target_hour, 1)
    load_utc = utc_hours(load["ts_utc"], "regional_load_hourly.ts_utc")
    for country in BIDDING_ZONES:
        selected = load["country_code"].eq(country)
        values = pd.Series(
            load.loc[selected, "load_actual_mw"].to_numpy(),
            index=pd.DatetimeIndex(load_utc[selected]),
        )
        result[f"f_load_{country.lower()}_same_hour_d_minus_1"] = values.reindex(keys).to_numpy()
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real to build real regional inputs")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    start = config.TRAIN_START.tz_convert("UTC")
    end = SNAPSHOT_END.tz_convert(config.LOCAL_TZ).normalize().tz_convert("UTC")
    price_frames = []
    price_reports = {}
    try:
        for country, zone in BIDDING_ZONES.items():
            native = fetch_snapshot_prices(start, end, bidding_zone=zone)
            hourly = to_hourly(native)
            if hourly.empty:
                raise ValueError(f"No complete price hours for {country}")
            price_reports[country] = price_coverage(native, hourly, start, end)
            price_frames.append(hourly.assign(country_code=country, bidding_zone=zone))

        prices = pd.concat(price_frames, ignore_index=True).astype(
            {
                "country_code": "string",
                "bidding_zone": "string",
            }
        )
        load = fetch_power_stats_load()
        features = add_regional_features(forecast_grid(start, end), prices, load)
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(1, f"Regional market build failed: {exc}\n")

    outputs = {
        "regional_prices_hourly.parquet": prices,
        "regional_load_hourly.parquet": load,
        "regional_market_features.parquet": features,
    }
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        frame.to_parquet(config.PROCESSED_DIR / name, index=False)

    report = {
        "bidding_zones": BIDDING_ZONES,
        "price_snapshot_revision": REVISION,
        "prices_by_country": price_reports,
        "load_start_utc": LOAD_START.isoformat(),
        "load_end_exclusive_utc": LOAD_END.isoformat(),
        "load_rows_by_country": load["country_code"].value_counts().to_dict(),
        "load_source_sha256_by_year": LOAD_FILE_SHA256,
        "feature_non_null_rows": features.drop(columns=list(FORECAST_KEYS)).count().to_dict(),
        "outputs": {
            name: {
                "rows": len(frame),
                "bytes": (config.PROCESSED_DIR / name).stat().st_size,
                "sha256": sha256_file(config.PROCESSED_DIR / name),
            }
            for name, frame in outputs.items()
        },
    }
    path = config.PROCESSED_DIR / "regional_market_manifest.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, frame in outputs.items():
        print(f"{name}: {len(frame):,} rows")
    print(f"Coverage and hashes: {path}")


if __name__ == "__main__":
    main()
