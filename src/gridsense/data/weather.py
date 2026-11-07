"""GFS archived forecast offsets, conservatively selected for the daily issue cutoff.

Previous Runs are fixed lead-time chunks, NOT runs frozen on a local issue date.
Only use offsets whose latest possible initialization plus a 12-hour assumed
publication buffer precedes the issue. Unsupported offsets stay NaN. Historical
publication timestamps are not supplied: this is a documented approximation,
not independently verified operational-vintage availability.
"""

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gridsense import config, io
from gridsense.schemas import WEATHER_FC

API_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
MODEL = "gfs_global"
DEFAULT_LOCATIONS = ("bucuresti", "constanta", "craiova", "timisoara")
PUBLICATION_BUFFER_HOURS = 12
MAX_OFFSET = 7
VARIABLES = {
    "shortwave_radiation": ("ghi_wm2", "W/m²"),
    "cloud_cover": ("cloud_cover_pct", "%"),
    "wind_speed_100m": ("wind100_ms", "m/s"),
    "temperature_2m": ("temp_c", "°C"),
}
PHYSICAL_BOUNDS = {"ghi_wm2": (0, 2000), "cloud_cover_pct": (0, 100),
                   "wind100_ms": (0, 150), "temp_c": (-100, 70)}
SOURCE_KEYS = ["issue_date", "target_ts_utc", "lead_days", "location"]


def select_offsets(target: pd.Series, issue: pd.Series) -> pd.Series:
    """Smallest supported-age candidate; values >7 must NOT be fetched or filled."""
    age = target - issue + pd.Timedelta(hours=PUBLICATION_BUFFER_HOURS)
    return np.ceil(age / pd.Timedelta(days=1)).clip(lower=1).astype("int64")


def parse_forecasts(payload: dict, location: str, retrieved_at: pd.Timestamp) -> pd.DataFrame:
    """Normalize one location's response without filling unsupported dates/offsets."""
    if payload.get("utc_offset_seconds") != 0:
        raise ValueError("Weather responses must use UTC")
    hourly, units = payload["hourly"], payload["hourly_units"]
    if units.get("time") != "unixtime":
        raise ValueError("Weather timestamps must be Unix UTC seconds")
    target = pd.Series(pd.to_datetime(hourly["time"], unit="s", utc=True).as_unit("ns"))
    if target.duplicated().any() or not target.eq(target.dt.floor("h")).all():
        raise ValueError("Weather target timestamps must be unique UTC hours")
    local_day = target.dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    values = {}
    for variable, (_, unit) in VARIABLES.items():
        columns = []
        for offset in range(1, MAX_OFFSET + 1):
            name = f"{variable}_previous_day{offset}"
            if units.get(name) != unit:
                raise ValueError(f"Unexpected units for {name}: {units.get(name)}")
            data = np.asarray(hourly[name], dtype=float)
            if len(data) != len(target) or np.isinf(data).any():
                raise ValueError(f"Invalid forecast array for {name}")
            if variable == "shortwave_radiation":
                # API radiation at t is the preceding-hour mean. Our delivery hour starts at t,
                # so take radiation at t+1, never shifting between forecast offsets.
                data = pd.Series(data, index=pd.DatetimeIndex(target)).reindex(
                    pd.DatetimeIndex(target + pd.Timedelta(hours=1))
                ).to_numpy()
            columns.append(data)
        values[variable] = np.column_stack(columns)

    frames = []
    for horizon in config.HORIZONS_DAYS:
        issue_date = local_day - pd.Timedelta(days=horizon)
        issue = (issue_date + pd.Timedelta(hours=config.ISSUE_HOUR)).dt.tz_localize(
            config.LOCAL_TZ
        ).dt.tz_convert("UTC")
        # Radiation describes [target,target+1h); guard the newest valid time used by any field.
        interval_end = target + pd.Timedelta(hours=1)
        offsets = select_offsets(interval_end, issue)
        supported = offsets.le(MAX_OFFSET)
        latest_init = (interval_end - pd.to_timedelta(offsets, unit="D")).where(supported)
        out = pd.DataFrame({
            "issue_date": issue_date, "target_ts_utc": target,
            "lead_days": horizon, "location": location,
            "source": "open_meteo_previous_runs", "source_model": MODEL,
            "source_offset_days": offsets,
            "source_initialization_upper_bound_utc": latest_init,
            "assumed_available_by_utc": latest_init + pd.Timedelta(hours=PUBLICATION_BUFFER_HOURS),
            "retrieved_at_utc": retrieved_at,
            "source_invalid_values": 0,
        })
        for variable, (column, _) in VARIABLES.items():
            chosen = np.full(len(target), np.nan)
            idx = np.flatnonzero(supported.to_numpy())
            chosen[idx] = values[variable][idx, offsets.iloc[idx].to_numpy() - 1]
            low, high = PHYSICAL_BOUNDS[column]
            invalid = ~np.isnan(chosen) & ((chosen < low) | (chosen > high))
            out["source_invalid_values"] += invalid.astype("int64")
            # The live archive contains e.g. 101% cloud. Preserve raw evidence, but do not
            # silently clamp or feed impossible physical values into model features.
            chosen[invalid] = np.nan
            out[column] = chosen
        frames.append(out)
    table = pd.concat(frames, ignore_index=True).astype(WEATHER_FC)
    validate_forecasts(table)
    return table


def validate_forecasts(table: pd.DataFrame) -> None:
    """Validate selected offsets, cutoff assumptions, horizon keys, and physical units."""
    if table.duplicated(SOURCE_KEYS).any():
        raise ValueError("Duplicate weather forecast keys")
    target = table["target_ts_utc"]
    expected_day = target.dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    if not (expected_day - table["issue_date"]).eq(
        pd.to_timedelta(table["lead_days"], unit="D")
    ).all():
        raise ValueError("Weather horizon does not match its local issue date")
    issue = (table["issue_date"] + pd.Timedelta(hours=config.ISSUE_HOUR)).dt.tz_localize(
        config.LOCAL_TZ
    ).dt.tz_convert("UTC")
    non_null = table[list(WEATHER_FC)[4:]].notna().any(axis=1)
    if "assumed_available_by_utc" in table:
        available = table["assumed_available_by_utc"]
        if (non_null & (available.isna() | available.gt(issue))).any():
            raise ValueError("Forecast could have become available after the issue cutoff")
        interval_end = target + pd.Timedelta(hours=1)
        selected = select_offsets(interval_end, issue)
        if not table["source_offset_days"].eq(selected).all():
            raise ValueError("Weather source offsets violate the conservative selection rule")
        init = table["source_initialization_upper_bound_utc"]
        supported = selected.le(MAX_OFFSET)
        expected_init = (interval_end - pd.to_timedelta(selected, unit="D")).where(supported)
        if not init.equals(expected_init):
            raise ValueError("Incorrect source initialization upper bounds")
        if not available.equals(init + pd.Timedelta(hours=PUBLICATION_BUFFER_HOURS)):
            raise ValueError("Incorrect forecast availability assumptions")
        if (non_null & ~supported).any():
            raise ValueError("Unsupported forecast offsets must remain missing")
    for column, (low, high) in PHYSICAL_BOUNDS.items():
        values = table[column].dropna()
        if not values.between(low, high).all():
            raise ValueError(f"Weather values outside plausible range for {column}")


def _month_ranges(start: pd.Timestamp, end: pd.Timestamp):
    cursor = start.normalize()
    while cursor < end:
        next_month = cursor.replace(day=1) + pd.offsets.MonthBegin(1)
        stop = min(next_month, end)
        yield cursor.date(), (stop - pd.Timedelta(nanoseconds=1)).date()
        cursor = next_month


def fetch_weather_forecasts(
    start: pd.Timestamp, end: pd.Timestamp, *, locations: tuple[str, ...] = DEFAULT_LOCATIONS,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """Forecast target hours in [start,end), UTC; monthly multi-location cached requests.

    Only the existing WEATHER_FC columns are contractual. Additional provenance columns
    are preserved in the Parquet without changing the shared schema.
    """
    if start.tz is None or end.tz is None or end <= start:
        raise ValueError("Weather bounds must be timezone-aware, with end after start")
    if not locations or len(set(locations)) != len(locations):
        raise ValueError("Choose distinct weather locations")
    for location in locations:
        if location not in config.WEATHER_POINTS:
            raise ValueError(f"Unknown weather location: {location}")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    cache = cache_dir or config.RAW_DIR / "weather_forecasts" / MODEL
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    retry = Retry(total=3, status_forcelist=(500, 502, 503, 504), backoff_factor=0.5)
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        for first, last in _month_ranges(start, end):
            params = {
                "latitude": ",".join(str(config.WEATHER_POINTS[p][0]) for p in locations),
                "longitude": ",".join(str(config.WEATHER_POINTS[p][1]) for p in locations),
                "start_date": str(first), "end_date": str(last + pd.Timedelta(days=1)),
                "hourly": ",".join(f"{v}_previous_day{n}" for v in VARIABLES
                                   for n in range(1, MAX_OFFSET + 1)),
                "models": MODEL, "timezone": "UTC", "wind_speed_unit": "ms",
                "timeformat": "unixtime",
            }
            request_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
            path = cache / f"{request_hash}.json"
            if path.exists():
                envelope = json.loads(path.read_text())
                if envelope["params"] != params:
                    raise ValueError(f"Weather cache request mismatch: {path.name}")
            else:
                print(f"Fetching archived {MODEL}: {first}..{last}, {len(locations)} points", flush=True)
                response = session.get(API_URL, params=params, timeout=(15, 180))
                response.raise_for_status()
                envelope = {"params": params, "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                            "payload": response.json()}
                # Cache only successful responses; no observed-weather fallback on errors.
                path.write_text(json.dumps(envelope, allow_nan=False))
            payloads = envelope["payload"]
            if isinstance(payloads, dict):
                payloads = [payloads]
            if len(payloads) != len(locations):
                raise ValueError("Weather API returned an unexpected number of locations")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            for location, payload in zip(locations, payloads, strict=True):
                lat, lon, _ = config.WEATHER_POINTS[location]
                if abs(payload["latitude"] - lat) > 1 or abs(payload["longitude"] - lon) > 1:
                    raise ValueError("Weather API location order/coordinates mismatch")
                frame = parse_forecasts(payload, location, pd.Timestamp(envelope["retrieved_at_utc"]))
                # The extra response day is only for end-of-month radiation alignment.
                first_ts = pd.Timestamp(first, tz="UTC")
                last_ts = (pd.Timestamp(last) + pd.Timedelta(days=1)).tz_localize("UTC")
                frame = frame[frame["target_ts_utc"].ge(first_ts) & frame["target_ts_utc"].lt(last_ts)]
                frames.append(frame.assign(request_sha256=request_hash, raw_sha256=digest))
    table = pd.concat(frames, ignore_index=True)
    table = table[table["target_ts_utc"].ge(start) & table["target_ts_utc"].lt(end)]
    table = table.sort_values(SOURCE_KEYS, ignore_index=True)
    validate_forecasts(table)
    return table


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=config.TRAIN_START.date())
    parser.add_argument("--end", type=date.fromisoformat, default=config.VAL_END.date())
    parser.add_argument("--locations", nargs="+", choices=list(config.WEATHER_POINTS),
                        default=list(DEFAULT_LOCATIONS))
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Use real mode for archived weather forecasts")
    start = pd.Timestamp(args.start, tz=config.LOCAL_TZ).tz_convert("UTC")
    end = (pd.Timestamp(args.end) + pd.Timedelta(days=1)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    table = fetch_weather_forecasts(start, end, locations=tuple(args.locations))
    if not table[[column for column, _ in VARIABLES.values()]].notna().any().any():
        raise SystemExit("No archived forecast values in this range; no output written")
    destination = config.PROCESSED_DIR / "weather_fc.parquet"
    if destination.exists():
        current = io.read("weather_fc")
        if "source_model" not in current or not current["source_model"].eq(MODEL).all():
            raise SystemExit("Existing weather_fc has different provenance; preserve/reconcile it first")
        if set(current["location"]) != set(args.locations):
            raise SystemExit("Existing weather_fc has different locations; preserve/reconcile it first")
        if table["target_ts_utc"].min() > current["target_ts_utc"].min() or table["target_ts_utc"].max() < current["target_ts_utc"].max():
            raise SystemExit("Refusing to replace existing weather_fc with a shorter date range")
    io.write(table, "weather_fc")
    availability = table.groupby("lead_days")[list(WEATHER_FC)[4:]].agg(lambda x: float(x.notna().mean()))
    manifest = {
        "source_url": API_URL, "model": MODEL, "locations": args.locations,
        "target_start_utc": start.isoformat(), "target_end_exclusive_utc": end.isoformat(),
        "rows": len(table), "publication_buffer_hours": PUBLICATION_BUFFER_HOURS,
        "invalid_physical_values_masked": int(table["source_invalid_values"].sum()),
        "historical_publication_verified": False, "observed_weather_used": False,
        "offset_rule": "ceil((delivery_hour_end - issue_time + publication_buffer) / 24h); offsets >7 are missing",
        "availability_by_horizon": availability.to_dict(orient="index"),
        "raw_files": table[["request_sha256", "raw_sha256"]].drop_duplicates().to_dict("records"),
        "notes": ["Older runs are selected; these are not exact 10:00 issue snapshots.",
                  "12 hours is an assumed buffer, not verified historical publication latency.",
                  "2023 may only contain temperature; unsupported variables remain missing.",
                  "Previous Runs only offers offsets 1..7; late long-horizon hours are unavailable.",
                  "Radiation at t+1 is aligned to delivery hour [t,t+1); other fields are at t.",
                  "Impossible physical values are masked to NaN; unmodified responses remain cached."],
    }
    (config.PROCESSED_DIR / "weather_forecasts_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[{config.DATA_MODE}] weather_fc: {len(table):,} rows; no observed weather used")
    print(availability.round(3).to_string())


if __name__ == "__main__":
    main()
