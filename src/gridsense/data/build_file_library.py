"""Rebuild real market and grid Parquet tables from locally selected ENTSO-E extracts."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.data.build import local_midnight, price_coverage
from gridsense.data.build_grid import grid_from_regional_load
from gridsense.data.build_regional import (
    BIDDING_ZONES,
    FORECAST_KEYS,
    LOAD_END,
    LOAD_FILE_SHA256,
    add_regional_features,
    forecast_grid,
    sha256_file,
)
from gridsense.data.entsoe import RESOLUTIONS, normalize_native, to_hourly
from gridsense.schemas import GRID_HOURLY, TABLES

SOURCE = "entsoe_file_library"
DEFAULT_SELECTION = config.RAW_DIR / SOURCE / "selected"
ACTUAL_LOAD_FOLDER = "ActualTotalLoad_6.1.A_r3"
NEIGHBOR_ZONES = [BIDDING_ZONES[country] for country in ("HU", "BG")]
AREA = {"AreaCode": "area_code", "AreaMapCode": "country_code"}
UPDATED = {"UpdateTime(UTC)": "updated_at_utc"}
INTERVAL = {"DateTime(UTC)": "ts_utc", "ResolutionCode": "resolution", **UPDATED}
LOAD = {**AREA, **INTERVAL, "TotalLoad[MW]": "load_mw"}
PRICE_KEY = ["bidding_zone", "ts_utc", "sequence"]
REGIONAL_KEY = ["country_code", "ts_utc"]
EXPORTS = {
    "prices": (
        {
            **INTERVAL,
            "AreaCode": "bidding_zone",
            "AreaMapCode": "country_code",
            "InstanceCode": "instance_code",
            "ContractType": "contract_type",
            "Sequence": "sequence",
            "Currency": "currency",
            "Price[Currency/MWh]": "price_eur_mwh",
        },
        PRICE_KEY,
    ),
    "actual_load": (LOAD, ["area_code", "ts_utc"]),
    "day_ahead_load": (LOAD, ["area_code", "ts_utc", "updated_at_utc"]),
    "generation": (
        {
            **AREA,
            **INTERVAL,
            "ProductionType": "production_type",
            "ActualGenerationOutput[MW]": "generation_mw",
            "ActualConsumption[MW]": "consumption_mw",
        },
        ["area_code", "production_type", "ts_utc"],
    ),
    "week_ahead_load": (
        {
            **AREA,
            **INTERVAL,
            "ContractType": "contract_type",
            "MinimumLoadForecast[MW]": "min_load_mw",
            "MaximumLoadForecast[MW]": "max_load_mw",
        },
        ["area_code", "ts_utc", "updated_at_utc"],
    ),
    "installed_capacity": (
        {
            **AREA,
            **UPDATED,
            "Year": "year",
            "TimeZone": "timezone",
            "ProductionType": "production_type",
            "AggregatedInstalledCapacity[MW]": "installed_capacity_mw",
        },
        ["area_code", "year", "production_type"],
    ),
    "hydro_storage": (
        {
            **AREA,
            **UPDATED,
            "Year": "year",
            "Week": "week",
            "TimeZone": "timezone",
            "StoredEnergy[MWh]": "stored_energy_mwh",
        },
        ["area_code", "year", "week"],
    ),
    "outages": (
        {
            **AREA,
            **UPDATED,
            "InstanceCode": "instance_code",
            "Version": "version",
            "OldVersion": "old_version",
            "StartOutage(UTC)": "outage_start_utc",
            "EndOutage(UTC)": "outage_end_utc",
            "StartTimeSeries(UTC)": "segment_start_utc",
            "EndTimeSeries(UTC)": "segment_end_utc",
            "VersionPublicationTimestamp(UTC)": "published_at_utc",
            "Status": "status",
            "Type": "outage_type",
            "AssetCode": "asset_code",
            "AssetName": "asset_name",
            "AssetType": "asset_type",
            "ProductionType": "production_type",
            "AvailableCapacity[MW]": "available_capacity_mw",
            "Reason": "reason",
            "Comment": "comment",
        },
        [
            "area_code",
            "instance_code",
            "version",
            "asset_code",
            "segment_start_utc",
            "segment_end_utc",
        ],
    ),
    "physical_flows": (
        {
            **INTERVAL,
            "OutAreaCode": "out_area_code",
            "InAreaCode": "in_area_code",
            "OutAreaMapCode": "out_country_code",
            "InAreaMapCode": "in_country_code",
            "Flow[MW]": "flow_mw",
        },
        ["out_area_code", "in_area_code", "ts_utc"],
    ),
}


def unique_key(frame: pd.DataFrame, key: list[str], name: str) -> None:
    if frame.empty or frame[key].isna().any().any():
        raise ValueError(f"{name}: empty table or missing key values for {key}")
    if frame.duplicated(key).any():
        raise ValueError(f"{name}: conflicting records for {key}")


def read_export(
    root: Path, name: str, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.DataFrame, dict]:
    columns, key = EXPORTS[name]
    paths = sorted((root / name).glob("*.csv.gz"))
    if not paths:
        raise ValueError(f"No selected extracts for {name} in {root}")

    if name == "actual_load":
        archive_dir = root.parent / ACTUAL_LOAD_FOLDER
        if archive_dir.is_dir() and end > LOAD_END:
            last = end - pd.Timedelta(nanoseconds=1)
            months = pd.period_range(LOAD_END.tz_localize(None), last.tz_localize(None), freq="M")
            paths.extend(
                archive_dir / f"{month:%Y_%m}_{ACTUAL_LOAD_FOLDER}.csv.zip" for month in months
            )

    frames = []
    for path in paths:
        part = pd.read_csv(
            path, sep="\t", usecols=list(columns), dtype="string", keep_default_na=False
        )
        for column in part:
            part[column] = part[column].str.strip().replace("", pd.NA)
        if path.suffix == ".zip":
            part = part.loc[part["AreaCode"].isin(NEIGHBOR_ZONES)]
        frames.append(part.rename(columns=columns).assign(source_file=path.name))
    frame = pd.concat(frames, ignore_index=True).astype({"source_file": "string"})

    for column in columns.values():
        if column.endswith("_utc"):
            frame[column] = pd.to_datetime(frame[column], format="mixed", utc=True).astype(
                "datetime64[ns, UTC]"
            )
        elif column.endswith(("_mw", "_mwh")):
            frame[column] = pd.to_numeric(frame[column]).astype("float64")
            if np.isinf(frame[column]).any():
                raise ValueError(f"{name}: non-finite values in {column}")
        elif column in ("year", "week", "version"):
            frame[column] = frame[column].astype("int64")

    if "ts_utc" in frame:
        frame = frame.loc[frame["ts_utc"].between(start, end, inclusive="left")]
        if name == "actual_load":
            neighbor = frame["area_code"].isin(NEIGHBOR_ZONES)
            frame = frame.loc[~neighbor | frame["ts_utc"].ge(LOAD_END)]
    elif name == "outages":
        frame = frame.loc[
            frame["segment_start_utc"].lt(end) & frame["segment_end_utc"].gt(start)
        ].copy()
        frame["old_version"] = (
            frame["old_version"].map({"true": True, "false": False}).astype("boolean")
        )
        if frame["published_at_utc"].isna().any():
            raise ValueError("Outages are missing publication timestamps")
    else:
        frame = frame.loc[frame["year"].between(config.TRAIN_START.year, config.TEST_END.year)]
        if name == "hydro_storage":
            weeks = pd.to_datetime(
                frame["year"].astype(str) + "-" + frame["week"].astype(str) + "-1",
                format="%G-%V-%u",
            )
            frame = frame.loc[weeks.lt(end.tz_convert(config.LOCAL_TZ).tz_localize(None))]

    selected_rows = len(frame)
    frame = frame.drop_duplicates(subset=list(columns.values()))
    if name == "prices":
        valid = frame["currency"].eq("EUR") & frame["contract_type"].eq("Day-ahead")
        if not valid.fillna(False).all() or frame["price_eur_mwh"].isna().any():
            raise ValueError("Expected day-ahead prices in EUR")
        frame = frame.assign(sequence=frame["sequence"].fillna("unspecified"))
        # Identical quotes are duplicate observations even with different instance codes.
        if frame.groupby(PRICE_KEY)["price_eur_mwh"].nunique(dropna=False).gt(1).any():
            raise ValueError("Conflicting day-ahead quotes within a market sequence")
        frame = frame.sort_values(["updated_at_utc", "instance_code"]).drop_duplicates(PRICE_KEY)

    unique_key(frame, key, name)
    return frame.sort_values(key, ignore_index=True), {
        "source_files": len(paths),
        "selected_rows": selected_rows,
        "duplicates_removed": selected_rows - len(frame),
    }


def complete_hours(frame: pd.DataFrame, value: str, *, resolution: str = "PT15M") -> pd.DataFrame:
    """Aggregate complete UTC hours and carry the latest source update."""
    unique_key(frame, ["ts_utc"], value)
    ts = frame["ts_utc"]
    step = RESOLUTIONS[resolution]
    if not (frame["resolution"].eq(resolution).fillna(False) & ts.eq(ts.dt.floor(step))).all():
        raise ValueError(f"{value}: expected aligned {resolution} data")
    groups = frame.groupby(ts.dt.floor("h"))
    hourly = groups.agg({value: "mean", "updated_at_utc": "max"})
    expected = pd.Timedelta(hours=1) // step
    complete = groups[value].count().eq(expected) & groups["updated_at_utc"].count().eq(expected)
    return hourly.loc[complete].reset_index()


def updated_by_next_issue(hourly: pd.DataFrame) -> pd.Series:
    """Require the source update by 10:00 local before using an actual as a D−1 lag."""
    local_day = hourly["ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None)
    cutoff = (
        local_day.dt.normalize() + pd.Timedelta(days=1, hours=config.ISSUE_HOUR)
    ).dt.tz_localize(config.LOCAL_TZ)
    return hourly["updated_at_utc"].le(cutoff)


def build_tables(
    selection: Path, destination: Path, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[dict, dict, dict, dict]:
    tables = {}
    inputs = {}
    for name, (_, key) in EXPORTS.items():
        frame, inputs[name] = read_export(selection, name, start, end)
        tables[f"{SOURCE}/{name}"] = (frame, key)

    all_prices = tables[f"{SOURCE}/prices"][0]
    price_reports = {}
    price_frames = []
    for country, zone in BIDDING_ZONES.items():
        market = all_prices.loc[all_prices["bidding_zone"].eq(zone)]
        native = normalize_native(
            market[["ts_utc", "price_eur_mwh", "resolution", "source_file"]].assign(
                document_id=pd.NA,
                revision_number=pd.NA,
                document_created_at_utc=pd.NaT,
            ),
            SOURCE,
            bidding_zone=zone,
        )
        hourly = to_hourly(native)
        price_reports[country] = price_coverage(native, hourly, start, end)
        if price_reports[country]["missing_native_intervals"]:
            raise ValueError(f"{country}: incomplete File Library price series")
        price_frames.append(hourly.assign(country_code=country, bidding_zone=zone))
        if country == "RO":
            tables["prices_native"] = (native, ["ts_utc"])
            tables["prices_hourly"] = (hourly, ["ts_utc"])

    prices = pd.concat(price_frames, ignore_index=True).astype(
        {"country_code": "string", "bidding_zone": "string"}
    )
    tables["regional_prices_hourly"] = (prices, REGIONAL_KEY)

    actual = tables[f"{SOURCE}/actual_load"][0]
    load_frames = []
    for country, zone in BIDDING_ZONES.items():
        rows = actual.loc[actual["area_code"].eq(zone)]
        if country != "RO" and rows.empty:
            continue
        resolution = "PT60M" if country == "BG" else "PT15M"
        hourly = complete_hours(rows, "load_mw", resolution=resolution).rename(
            columns={"load_mw": "load_actual_mw"}
        )
        if hourly["load_actual_mw"].lt(0).any():
            raise ValueError(f"{country}: expected nonnegative load")
        load_frames.append(hourly.assign(country_code=country, bidding_zone=zone, source=SOURCE))
    new_load = pd.concat(load_frames, ignore_index=True)
    old_load = pd.read_parquet(destination / "regional_load_hourly.parquet")
    unique_key(old_load, REGIONAL_KEY, "existing regional_load_hourly")
    # Keep pinned Power Statistics history on overlap and use File Library for missing hours.
    legacy = old_load.loc[old_load["source"].ne(SOURCE)]
    additions = new_load.loc[
        ~pd.MultiIndex.from_frame(new_load[REGIONAL_KEY]).isin(
            pd.MultiIndex.from_frame(legacy[REGIONAL_KEY])
        )
    ]
    load = (
        pd.concat([legacy, additions[legacy.columns]], ignore_index=True)
        .astype({"country_code": "string", "bidding_zone": "string", "source": "string"})
        .sort_values(REGIONAL_KEY, ignore_index=True)
    )
    load_keys = pd.MultiIndex.from_frame(load[REGIONAL_KEY])
    lost_keys = pd.MultiIndex.from_frame(old_load[REGIONAL_KEY]).difference(load_keys)
    if len(lost_keys):
        raise ValueError(
            f"Rebuild would lose {len(lost_keys)} existing load hours. Check local extracts."
        )
    tables["regional_load_hourly"] = (load, REGIONAL_KEY)

    actual_grid = grid_from_regional_load(load).drop(columns=["solar_actual_mw", "wind_actual_mw"])
    late_load = additions.loc[~updated_by_next_issue(additions)]
    late_hours = {"load_actual_mw": late_load.loc[late_load["country_code"].eq("RO"), "ts_utc"]}
    generation = tables[f"{SOURCE}/generation"][0]
    for fuel, value in (("Solar", "solar_actual_mw"), ("Wind Onshore", "wind_actual_mw")):
        rows = generation.loc[generation["production_type"].eq(fuel)]
        hourly = complete_hours(rows, "generation_mw")
        late_hours[value] = hourly.loc[~updated_by_next_issue(hourly), "ts_utc"]
        actual_grid = actual_grid.merge(
            hourly[["ts_utc", "generation_mw"]].rename(columns={"generation_mw": value}),
            on="ts_utc",
            how="outer",
            validate="one_to_one",
        )
    actual_grid = (
        actual_grid[list(GRID_HOURLY)].astype(GRID_HOURLY).sort_values("ts_utc", ignore_index=True)
    )
    tables[f"{SOURCE}/grid_actual_hourly"] = (actual_grid, ["ts_utc"])
    grid = actual_grid.copy()
    for value, hours in late_hours.items():
        grid.loc[grid["ts_utc"].isin(hours), value] = np.nan
    tables["grid_hourly"] = (grid, ["ts_utc"])

    feature_load = load.loc[~load_keys.isin(pd.MultiIndex.from_frame(late_load[REGIONAL_KEY]))]
    features = add_regional_features(forecast_grid(start, end), prices, feature_load)
    tables["regional_market_features"] = (features, list(FORECAST_KEYS))
    expected_hours = pd.date_range(start, end, freq="h", inclusive="left")
    coverage = {}
    for country in BIDDING_ZONES:
        missing = expected_hours.difference(load.loc[load["country_code"].eq(country), "ts_utc"])
        coverage[country] = {
            "missing_hours": len(missing),
            "missing_hours_since_power_stats_end": int((missing >= LOAD_END).sum()),
            "first_missing_hours_utc": [ts.isoformat() for ts in missing[:12]],
        }
    integration = {
        "legacy_load_rows_by_country": legacy["country_code"].value_counts().to_dict(),
        "file_library_load_hours_by_country": additions["country_code"].value_counts().to_dict(),
        "late_file_library_load_hours_by_country": late_load["country_code"]
        .value_counts()
        .to_dict(),
        "load_coverage_by_country": coverage,
        "grid_actual_non_null_hours": actual_grid.drop(columns="ts_utc").count().to_dict(),
        "grid_late_hours_excluded": {column: len(hours) for column, hours in late_hours.items()},
        "grid_non_null_hours": grid.drop(columns="ts_utc").count().to_dict(),
    }
    return tables, inputs, price_reports, integration


def build(selection: Path, destination: Path) -> None:
    start = local_midnight(config.TRAIN_START.date())
    end = local_midnight(config.TEST_END.date() + pd.Timedelta(days=1))
    tables, inputs, price_reports, integration = build_tables(selection, destination, start, end)
    with TemporaryDirectory(prefix=".entsoe-build-", dir=destination) as temporary:
        staged = Path(temporary)
        outputs = {}
        for name, (frame, key) in tables.items():
            unique_key(frame, key, name)
            if name in TABLES:
                io.check_columns(frame, name)
            path = staged / f"{name}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False)
            unique_key(pd.read_parquet(path, columns=key), key, name)
            outputs[f"{name}.parquet"] = {
                "rows": len(frame),
                "key": key,
                "duplicate_keys": 0,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }

        reports = {
            "prices_quality.json": {
                **price_reports["RO"],
                "source": SOURCE,
                "snapshot_revision": None,
                "bidding_zone": config.BIDDING_ZONE,
                "unit": "EUR/MWh",
            },
            "regional_market_manifest.json": {
                "bidding_zones": BIDDING_ZONES,
                "price_source": SOURCE,
                "price_snapshot_revision": None,
                "prices_by_country": price_reports,
                "load_source_sha256_by_year": LOAD_FILE_SHA256,
                "power_stats_load_end_exclusive_utc": LOAD_END.isoformat(),
                "load_coverage_by_country": integration["load_coverage_by_country"],
                "load_rows_by_country": tables["regional_load_hourly"][0]["country_code"]
                .value_counts()
                .to_dict(),
                "feature_non_null_rows": tables["regional_market_features"][0]
                .drop(columns=list(FORECAST_KEYS))
                .count()
                .to_dict(),
                "outputs": {
                    name: info for name, info in outputs.items() if name.startswith("regional_")
                },
            },
            f"{SOURCE}/manifest.json": {
                "start_utc": start.isoformat(),
                "end_exclusive_utc": end.isoformat(),
                "inputs": inputs,
                "outputs": outputs,
                "integration": integration,
            },
        }
        for name, report in reports.items():
            (staged / name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for name in (*outputs, *reports):
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            (staged / name).replace(path)
    print(
        f"Wrote {len(outputs)} unique-key Parquet tables. See {destination / SOURCE / 'manifest.json'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    args = parser.parse_args()
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real to build real market and grid data")
    build(args.selection, config.PROCESSED_DIR)


if __name__ == "__main__":
    main()
