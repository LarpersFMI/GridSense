"""Opt-in regional weather grid from the same archived GFS offsets and cutoff rule.

Points are the configured RO/HU/BG locations (Moldova is outside SDAC coupling). Country
aggregates weight points equally: no sourced per-region capacity table exists yet, so do
not substitute guessed capacity weights. No observed weather is used.
"""

import time

import pandas as pd

from gridsense import config
from gridsense.data import weather
from gridsense.data.weather import fetch_weather_forecasts, validate_forecasts

GRID_COUNTRIES = {"Romania": "ro", "Hungary": "hu", "Bulgaria": "bg"}
GRID_PREFIX = "f_wgrid_"
WEATHER_KEYS = ["issue_date", "horizon_days", "target_ts_utc"]
JOIN_KEYS = ["issue_ts", "target_ts_utc", "horizon_days"]
# Requests over 10 variables or 2 weeks count as several Open-Meteo calls; stay under the hourly cap.
REQUEST_PACE_SECONDS = 120


def grid_locations() -> dict[str, tuple[str, ...]]:
    return {
        code: tuple(p for p, (_, _, c) in config.WEATHER_POINTS.items() if c == country)
        for country, code in GRID_COUNTRIES.items()
    }


def fetch_grid(start: pd.Timestamp, end: pd.Timestamp, existing: pd.DataFrame | None = None,
               pace_seconds: float = REQUEST_PACE_SECONDS) -> pd.DataFrame:
    """Archived forecasts for every grid point; reuses `existing` rows for points it has."""
    have = set() if existing is None else set(existing["location"])
    needed = tuple(p for points in grid_locations().values() for p in points if p not in have)
    frames = [] if existing is None else [existing[existing["location"].isin(
        [p for points in grid_locations().values() for p in points])]]
    if needed:
        # Same month windows as one full call, so the cache keys match and later runs are offline.
        for first, last in weather._month_ranges(start.tz_convert("UTC"), end.tz_convert("UTC")):
            began = time.monotonic()
            fetch_weather_forecasts(pd.Timestamp(first, tz="UTC"),
                                    pd.Timestamp(last, tz="UTC") + pd.Timedelta(days=1), locations=needed)
            if time.monotonic() - began > 5:
                time.sleep(pace_seconds)
        frames.append(fetch_weather_forecasts(start, end, locations=needed))
    table = pd.concat(frames, ignore_index=True)
    table = table[table["target_ts_utc"].ge(start) & table["target_ts_utc"].lt(end)]
    validate_forecasts(table.reset_index(drop=True))
    return table.reset_index(drop=True)


def grid_features(weather_fc: pd.DataFrame, countries: tuple[str, ...] = ("ro", "hu", "bg")) -> pd.DataFrame:
    """Country means (and RO radiation spread) per forecast key; NaN unless every point is present."""
    if not weather_fc["lead_days"].isin(config.HORIZONS_DAYS).all():
        raise ValueError("Weather grid needs D+1…D+7 forecast leads, not observed weather")
    validate_forecasts(weather_fc.reset_index(drop=True))
    points = grid_locations()
    if weather_fc.duplicated(weather.SOURCE_KEYS).any():
        raise ValueError("Duplicate weather grid forecast keys")
    short = {"ghi_wm2": "ghi", "cloud_cover_pct": "cloud", "wind100_ms": "wind100", "temp_c": "temp"}
    wide = weather_fc.set_index(["issue_date", "lead_days", "target_ts_utc", "location"])[
        list(short)
    ].unstack("location")
    out = pd.DataFrame(index=wide.index)
    for code in countries:
        missing = set(points[code]) - set(weather_fc["location"])
        if missing:
            raise ValueError(f"Weather grid is missing {code} points: {sorted(missing)}")
        for column, name in short.items():
            values = wide[column][list(points[code])]
            out[f"{GRID_PREFIX}{code}_{name}_mean"] = values.mean(axis=1, skipna=False)
            if code == "ro" and name == "ghi":
                out[f"{GRID_PREFIX}ro_ghi_std"] = values.std(axis=1, skipna=False)
    return out.reset_index().rename(columns={"lead_days": "horizon_days"})


def join_grid_features(training: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Left join on forecast keys; preserves every row, index, label and existing feature."""
    if overlap := set(features.columns).intersection(training.columns) - set(WEATHER_KEYS):
        raise ValueError(f"Weather grid features already exist: {sorted(overlap)}")
    if features.duplicated(WEATHER_KEYS).any():
        raise ValueError("Weather grid features must be unique per forecast key")
    left = training[JOIN_KEYS].copy()
    left["issue_date"] = left["issue_ts"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    left["target_ts_utc"] = left["target_ts_utc"].dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
    left["horizon_days"] = left["horizon_days"].astype("int64")
    right = features.astype({"target_ts_utc": "datetime64[ns, UTC]", "horizon_days": "int64"})
    merged = left.merge(right, on=WEATHER_KEYS, how="left", validate="many_to_one")
    added = merged.drop(columns=[*JOIN_KEYS, "issue_date"]).set_axis(training.index)
    return pd.concat([training, added], axis=1)
