import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.splits import assign_split


def calculate_air_density(temp_c: pd.Series, pressure_hpa: pd.Series) -> pd.Series:
    """Calculates dry air density (kg/m^3) using p / (R * T)."""
    temp_k = temp_c + 273.15
    pressure_pa = pressure_hpa * 100.0
    R_specific = 287.058
    return pressure_pa / (R_specific * temp_k)


def calculate_solar_elevation(
    ts_series: pd.Series, lats: pd.Series, lons: pd.Series
) -> pd.Series:
    """Computes approximate solar elevation angle (degrees) for clear-sky solar proxy."""
    day_of_year = ts_series.dt.dayofyear
    hour = ts_series.dt.hour + ts_series.dt.minute / 60.0

    # Solar declination angle
    declination = 23.45 * np.sin(np.radians((360.0 / 365.25) * (day_of_year - 81.0)))

    # Equation of time & Local Solar Time offset
    time_offset = lons * 4.0  # minutes per degree longitude
    solar_time = hour + (time_offset / 60.0)
    hour_angle = (solar_time - 12.0) * 15.0

    lat_rad = np.radians(lats)
    dec_rad = np.radians(declination)
    ha_rad = np.radians(hour_angle)

    sin_elevation = np.sin(lat_rad) * np.sin(dec_rad) + np.cos(lat_rad) * np.cos(
        dec_rad
    ) * np.cos(ha_rad)

    return np.degrees(np.arcsin(np.clip(sin_elevation, -1.0, 1.0)))


def engineer_location_features(df_weather: pd.DataFrame) -> pd.DataFrame:
    """Applies point-level physical transformations on forecasted weather variables."""
    df = df_weather.copy()

    # Air Density & Wind Power Density (W/m^2) = 0.5 * rho * v^3
    rho = calculate_air_density(df["temp_c"], df["pressure_hpa"])
    df["wind_power_density"] = 0.5 * rho * (df["wind10_ms"] ** 3)

    # Decompose wind vectors into U (East-West) and V (North-South) components
    wind_rad = np.radians(df["wind_dir_deg"])
    df["wind_u"] = -df["wind10_ms"] * np.sin(wind_rad)
    df["wind_v"] = -df["wind10_ms"] * np.cos(wind_rad)

    # Solar Irradiance Proxy (Clear-sky geometry combined with forecasted cloud opacity)
    sol_elev = calculate_solar_elevation(
        df["target_ts_utc"], df["latitude"], df["longitude"]
    )
    clear_sky_potential = np.maximum(0.0, np.sin(np.radians(sol_elev)))
    df["solar_proxy_wm2"] = clear_sky_potential * (
        1.0 - (df["cloud_cover_pct"] / 100.0)
    )

    # Degree Hours (Demand proxies)
    df["heating_degree_hour"] = np.maximum(0.0, 18.0 - df["temp_c"])
    df["cooling_degree_hour"] = np.maximum(0.0, df["temp_c"] - 22.0)

    return df


def build_issue_date_price_features(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Engineers price memory features strictly anchored to issue_date (10:00 cutoff on day D).

    Available information on Day D at 10:00:
      - Latest settled price data is for Day D (up to 24h of Day D).
    """
    df_p = prices_df.copy()
    price_col = "price_mean" if "price_mean" in df_p.columns else "price"

    # Convert UTC target time to local time to establish local calendar date
    df_p["local_dt"] = df_p["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    df_p["issue_date"] = pd.to_datetime(df_p["local_dt"].dt.date)

    # 1. Daily macro price metrics for Day D (latest known day at issue time)
    daily_stats = (
        df_p.groupby("issue_date")[price_col]
        .agg(
            price_issue_day_mean="mean",
            price_issue_day_min="min",
            price_issue_day_max="max",
            price_issue_day_std="std",
        )
        .reset_index()
    )

    # 2. Historical price lags relative to issue date D (Day D-1, Day D-7)
    daily_stats["price_issue_lag_1d_mean"] = daily_stats["price_issue_day_mean"].shift(1)
    daily_stats["price_issue_lag_7d_mean"] = daily_stats["price_issue_day_mean"].shift(7)
    daily_stats["price_issue_momentum_1d"] = (
        daily_stats["price_issue_day_mean"] - daily_stats["price_issue_lag_1d_mean"]
    )

    return daily_stats


def build_working_dataset():
    print("1. Loading raw parquet datasets...")
    weather_df = io.read("weather_hourly")
    prices_df = io.read("prices_hourly")

    # Ensure UTC timezone awareness for timestamps
    weather_df["target_ts_utc"] = pd.to_datetime(weather_df["target_ts_utc"], utc=True)
    prices_df["target_ts_utc"] = pd.to_datetime(
        prices_df["target_ts_utc"]
        if "target_ts_utc" in prices_df.columns
        else prices_df["ts_utc"],
        utc=True,
    )

    # Calculate issue_date & lead_days if missing from raw weather table
    if "issue_date" not in weather_df.columns:
        local_ts = weather_df["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
        weather_df["issue_date"] = pd.to_datetime(
            local_ts.apply(
                lambda ts: ts.date()
                if ts.hour >= config.ISSUE_HOUR
                else (ts - pd.Timedelta(days=1)).date()
            )
        )
        target_date = pd.to_datetime(local_ts.dt.date)
        weather_df["lead_days"] = (target_date - weather_df["issue_date"]).dt.days

    print("2. Engineering physical forecast features (Wind Power, Solar Proxy, HDD/CDD)...")
    weather_df = engineer_location_features(weather_df)

    feature_cols = [
        "temp_c",
        "relative_humidity_pct",
        "precip_mm",
        "pressure_hpa",
        "cloud_cover_pct",
        "wind10_ms",
        "wind_power_density",
        "wind_u",
        "wind_v",
        "solar_proxy_wm2",
        "heating_degree_hour",
        "cooling_degree_hour",
    ]

    print("3. Pivoting forecasted weather across locations...")
    pivoted_df = weather_df.pivot(
        index=["target_ts_utc", "issue_date", "lead_days"],
        columns="location",
        values=feature_cols,
    )
    pivoted_df.columns = [f"{var}_{loc}" for var, loc in pivoted_df.columns]
    pivoted_df = pivoted_df.reset_index()

    print("4. Computing regional spatial aggregates (Romania & Neighbors)...")
    ro_locations = [
        loc
        for loc, (_, _, country) in config.WEATHER_POINTS.items()
        if country == "Romania"
    ]
    neighbor_locations = [
        loc
        for loc, (_, _, country) in config.WEATHER_POINTS.items()
        if country != "Romania"
    ]

    for var in ["temp_c", "wind10_ms", "wind_power_density", "solar_proxy_wm2"]:
        ro_cols = [f"{var}_{loc}" for loc in ro_locations if f"{var}_{loc}" in pivoted_df]
        neigh_cols = [
            f"{var}_{loc}" for loc in neighbor_locations if f"{var}_{loc}" in pivoted_df
        ]

        if ro_cols:
            pivoted_df[f"{var}_ro_mean"] = pivoted_df[ro_cols].mean(axis=1)
            pivoted_df[f"{var}_ro_min"] = pivoted_df[ro_cols].min(axis=1)
            pivoted_df[f"{var}_ro_max"] = pivoted_df[ro_cols].max(axis=1)

        if neigh_cols:
            pivoted_df[f"{var}_neighbors_mean"] = pivoted_df[neigh_cols].mean(axis=1)

    print("5. Generating leakage-free price memory features at issue_date level...")
    price_issue_features = build_issue_date_price_features(prices_df)

    print("6. Joining prices and issue-date price memory with weather panel...")
    # First join target price at target_ts_utc
    working_df = pd.merge(
        prices_df, pivoted_df, on="target_ts_utc", how="inner"
    )
    # Then join price features anchored to issue_date cutoff
    working_df = pd.merge(
        working_df, price_issue_features, on="issue_date", how="left"
    ).sort_values("target_ts_utc")

    print("7. Adding target hour temporal and cyclical features...")
    ts_local = working_df["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)

    working_df["hour"] = ts_local.dt.hour
    working_df["dayofweek"] = ts_local.dt.dayofweek
    working_df["dayofyear"] = ts_local.dt.dayofyear
    working_df["is_weekend"] = working_df["dayofweek"].isin([5, 6]).astype(int)

    # Cyclical representations
    working_df["hour_sin"] = np.sin(2 * np.pi * working_df["hour"] / 24.0)
    working_df["hour_cos"] = np.cos(2 * np.pi * working_df["hour"] / 24.0)
    working_df["dayofweek_sin"] = np.sin(2 * np.pi * working_df["dayofweek"] / 7.0)
    working_df["dayofweek_cos"] = np.cos(2 * np.pi * working_df["dayofweek"] / 7.0)
    working_df["dayofyear_sin"] = np.sin(2 * np.pi * working_df["dayofyear"] / 365.25)
    working_df["dayofyear_cos"] = np.cos(2 * np.pi * working_df["dayofyear"] / 365.25)

    print("8. Assigning canonical dataset splits via gridsense.splits...")
    # Strict compliance with Rule 10
    working_df["split"] = assign_split(working_df["target_ts_utc"])

    train_df = working_df[working_df["split"] == "train"].reset_index(drop=True)
    val_df = working_df[working_df["split"] == "val"].reset_index(drop=True)
    test_df = working_df[working_df["split"] == "test"].reset_index(drop=True)

    print(
        f"\nFeature Augmentation Complete (No Leakage):\n"
        f" - Train shape:      {train_df.shape}\n"
        f" - Validation shape: {val_df.shape}\n"
        f" - Test shape:       {test_df.shape}\n"
        f" - Total features:   {len(working_df.columns)}\n"
    )

    return train_df, val_df, test_df, working_df


if __name__ == "__main__":
    train_df, val_df, test_df, working_df = build_working_dataset()