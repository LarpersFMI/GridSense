"""Opt-in physical/calendar/price ideas rebuilt on issue-known forecast inputs.

Never reads observed weather or the upstream augmented table/ranking. Weather
transformations retain the selected Previous Runs offsets, missingness and cutoff
assumptions. Surface-air/10 m wind density is a proxy, not turbine generation;
solar potential/cloud proxy is dimensionless, not measured irradiance in W/m².
"""

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.data.weather import DEFAULT_LOCATIONS, SOURCE_KEYS, validate_forecasts
from gridsense.features.weather_grid import WEATHER_KEYS, join_grid_features

PREFIX = "f_feng_"
POINT_FEATURES = (
    "solar_potential", "solar_cloud_proxy", "heating_degree_c", "cooling_degree_c",
    "air_density_kgm3", "wind10_power_density_proxy_wm2", "wind10_u_ms", "wind10_v_ms",
)
DRY_AIR_GAS_CONSTANT = 287.058  # J/(kg K)


def solar_potential(target: pd.Series, latitude: pd.Series, longitude: pd.Series) -> pd.Series:
    """Approximate positive sine of solar elevation at the delivery-hour midpoint.

    Uses UTC, longitude and the standard fractional-year declination/equation-of-time
    approximation. All inputs are known in advance; output lies in [0, 1].
    """
    utc = (target + pd.Timedelta(minutes=30)).dt.tz_convert("UTC")
    hour = utc.dt.hour + utc.dt.minute / 60.0
    gamma = 2 * np.pi / 365.25 * (utc.dt.day_of_year - 1 + (hour - 12) / 24)
    equation = 229.18 * (
        0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma)
    )
    declination = (
        0.006918 - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma) + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma) + 0.00148 * np.sin(3 * gamma)
    )
    angle = np.deg2rad((hour * 60 + equation + 4 * longitude) / 4 - 180)
    lat = np.deg2rad(latitude)
    elevation_sine = np.sin(lat) * np.sin(declination) + (
        np.cos(lat) * np.cos(declination) * np.cos(angle)
    )
    return pd.Series(np.clip(np.asarray(elevation_sine, dtype=float), 0, 1), index=target.index)


def _optional(table: pd.DataFrame, column: str) -> pd.Series:
    return (table[column].astype(float) if column in table
            else pd.Series(np.nan, index=table.index, dtype=float))


def weather_features(weather_fc: pd.DataFrame,
                     locations: tuple[str, ...] = DEFAULT_LOCATIONS) -> pd.DataFrame:
    """Per-point nonlinear features and strict equal-point means on the forecast key."""
    io.check_columns(weather_fc, "weather_fc")
    if not locations or len(set(locations)) != len(locations):
        raise ValueError("Choose distinct configured forecast locations")
    if set(locations) - set(config.WEATHER_POINTS):
        raise ValueError("Unknown forecast location")
    if not weather_fc["lead_days"].isin(config.HORIZONS_DAYS).all():
        raise ValueError("Engineering requires D+1…D+7 archived forecasts, not observations")
    if "source" in weather_fc and not weather_fc["source"].eq("open_meteo_previous_runs").all():
        raise ValueError("Engineering requires archived Previous Runs forecasts, not observations")
    if weather_fc.duplicated(SOURCE_KEYS).any():
        raise ValueError("Duplicate weather forecast keys")
    validate_forecasts(weather_fc)
    points = weather_fc.loc[weather_fc["location"].isin(locations)].copy()
    # pandas preserves the input string dtype when mapping an empty Series.
    latitude = points["location"].map(
        {loc: value[0] for loc, value in config.WEATHER_POINTS.items()}).astype(float)
    longitude = points["location"].map(
        {loc: value[1] for loc, value in config.WEATHER_POINTS.items()}).astype(float)
    potential = solar_potential(points["target_ts_utc"], latitude, longitude)
    temperature = points["temp_c"]
    density = _optional(points, "pressure_hpa") * 100 / (
        DRY_AIR_GAS_CONSTANT * (temperature + 273.15)
    )
    speed = _optional(points, "wind10_ms")
    direction = np.deg2rad(_optional(points, "wind_dir_deg"))
    values = points[SOURCE_KEYS].assign(
        solar_potential=potential,
        solar_cloud_proxy=potential * (1 - points["cloud_cover_pct"] / 100),
        heating_degree_c=(config.HEATING_BASE_C - temperature).clip(lower=0),
        cooling_degree_c=(temperature - config.COOLING_BASE_C).clip(lower=0),
        air_density_kgm3=density,
        wind10_power_density_proxy_wm2=0.5 * density * speed ** 3,
        wind10_u_ms=-speed * np.sin(direction),
        wind10_v_ms=-speed * np.cos(direction),
    )
    wide = values.set_index(SOURCE_KEYS)[list(POINT_FEATURES)].unstack("location")
    out = pd.DataFrame(index=wide.index)
    for name in POINT_FEATURES:
        available = (pd.DataFrame(wide[name]) if name in wide.columns.get_level_values(0)
                     else pd.DataFrame(index=wide.index))
        per_point = available.reindex(columns=list(locations))
        for location in locations:
            out[f"{PREFIX}{name}_{location}"] = per_point[location]
        # Do not let a three-point mean masquerade as complete four-point coverage.
        out[f"{PREFIX}{name}_mean"] = per_point.mean(axis=1, skipna=False)
    measured = [f"{PREFIX}{name}_{location}" for name in POINT_FEATURES
                if name != "solar_potential" for location in locations]
    out[f"{PREFIX}missing_weather"] = out[measured].isna().any(axis=1).astype("int8")
    return out.reset_index().rename(columns={"lead_days": "horizon_days"})


def price_features(training: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Complete elapsed-hour windows strictly before the issue timestamp (not delivery)."""
    io.check_columns(prices, "prices_hourly")
    if prices["ts_utc"].duplicated().any():
        raise ValueError("Price memory requires unique UTC delivery hours")
    history = prices.set_index("ts_utc")["price_mean"].astype(float)
    issues = pd.DatetimeIndex(training["issue_ts"].unique())
    past = pd.DataFrame({
        hour: history.reindex(issues - pd.Timedelta(hours=hour)).to_numpy()
        for hour in range(1, max(config.PRICE_MEMORY_WINDOWS_HOURS) + 1)
    }, index=issues)
    out = pd.DataFrame(index=issues)
    for hours in config.PRICE_MEMORY_WINDOWS_HOURS:
        window = past.loc[:, range(1, hours + 1)]
        out[f"{PREFIX}price_recent_mean_{hours}h"] = window.mean(axis=1, skipna=False)
        out[f"{PREFIX}price_recent_std_{hours}h"] = window.std(axis=1, skipna=False)
    return out.reindex(training["issue_ts"]).set_axis(training.index)


def join_engineered_features(training: pd.DataFrame, weather_fc: pd.DataFrame,
                             prices: pd.DataFrame,
                             locations: tuple[str, ...] = DEFAULT_LOCATIONS) -> pd.DataFrame:
    """Keep all original keys/index/labels/features; only append fixed opt-in f_ columns."""
    if any(isinstance(column, str) and column.startswith(PREFIX) for column in training):
        raise ValueError("Engineered features already exist")
    keys = ["issue_ts", "target_ts_utc", "horizon_days"]
    if training.duplicated(keys).any():
        raise ValueError("Duplicate training forecast keys")
    local_issue = training["issue_ts"].dt.tz_convert(config.LOCAL_TZ)
    scheduled = local_issue.dt.hour.eq(config.ISSUE_HOUR) & (
        local_issue.dt.minute.eq(0) & local_issue.dt.second.eq(0)
        & local_issue.dt.microsecond.eq(0) & local_issue.dt.nanosecond.eq(0)
    )
    if not scheduled.all():
        raise ValueError("Engineering must use the configured daily issue cutoff")
    local_target = training["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    delta = (local_target.dt.tz_localize(None).dt.normalize()
             - local_issue.dt.tz_localize(None).dt.normalize())
    if (not training["horizon_days"].isin(config.HORIZONS_DAYS).all()
            or not delta.eq(pd.to_timedelta(training["horizon_days"], unit="D")).all()):
        raise ValueError("Training horizon does not match its local issue date")
    weather = weather_features(weather_fc, locations)
    if weather.duplicated(WEATHER_KEYS).any():
        raise ValueError("Duplicate engineered weather forecast keys")
    out = join_grid_features(training, weather)
    # A completely unmatched forecast key is missing too; never fill a weather value.
    out[f"{PREFIX}missing_weather"] = out[f"{PREFIX}missing_weather"].fillna(1).astype("int8")
    local = training["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    calendar = pd.DataFrame(index=training.index)
    for name, values, period in (("hour", local.dt.hour, 24),
                                  ("weekday", local.dt.day_of_week, 7)):
        calendar[f"{PREFIX}{name}_sin"] = np.sin(2 * np.pi * values / period)
        calendar[f"{PREFIX}{name}_cos"] = np.cos(2 * np.pi * values / period)
    return pd.concat([out, calendar, price_features(training, prices)], axis=1)