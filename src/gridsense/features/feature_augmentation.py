import numpy as np
import pandas as pd
from gridsense import config, io


def calculate_air_density(temp_c: pd.Series, pressure_hpa: pd.Series) -> pd.Series:
    temp_k = temp_c + 273.15
    pressure_pa = pressure_hpa * 100.0
    R_specific = 287.058
    return pressure_pa / (R_specific * temp_k)


def calculate_solar_elevation(
    ts_series: pd.Series, lats: pd.Series, lons: pd.Series
) -> pd.Series:
    """Computes approximate solar elevation angle (degrees) for solar radiation proxy."""
    day_of_year = ts_series.dt.dayofyear
    hour = ts_series.dt.hour + ts_series.dt.minute / 60.0

    # Solar declination angle
    declination = 23.45 * np.sin(np.radians((360 / 365) * (day_of_year - 81)))

    # Equation of time approximation & Local Solar Time
    time_offset = lons * 4.0  # minutes per degree longitude
    solar_time = hour + (time_offset / 60.0)
    hour_angle = (solar_time - 12.0) * 15.0  # degrees

    lat_rad = np.radians(lats)
    dec_rad = np.radians(declination)
    ha_rad = np.radians(hour_angle)

    sin_elevation = np.sin(lat_rad) * np.sin(dec_rad) + np.cos(lat_rad) * np.cos(
        dec_rad
    ) * np.cos(ha_rad)

    return np.degrees(np.arcsin(np.clip(sin_elevation, -1.0, 1.0)))


def engineer_location_features(df_weather: pd.DataFrame) -> pd.DataFrame:
    """Applies point-level physical transformations (Wind Power, Solar Proxy, HDD/CDD)."""
    df = df_weather.copy()

    # Air Density & Wind Power Density (W/m^2) = 0.5 * rho * v^3
    rho = calculate_air_density(df["temp_c"], df["pressure_hpa"])
    df["wind_power_density"] = 0.5 * rho * (df["wind10_ms"] ** 3)

    # Decompose wind vectors into U (East-West) and V (North-South) components
    wind_rad = np.radians(df["wind_dir_deg"])
    df["wind_u"] = -df["wind10_ms"] * np.sin(wind_rad)
    df["wind_v"] = -df["wind10_ms"] * np.cos(wind_rad)

    # Solar Proxy: Clear-sky potential combined with inverse cloud cover
    sol_elev = calculate_solar_elevation(
        df["target_ts_utc"], df["latitude"], df["longitude"]
    )
    clear_sky_potential = np.maximum(0.0, np.sin(np.radians(sol_elev)))
    df["solar_proxy_wm2"] = clear_sky_potential * (
        1.0 - (df["cloud_cover_pct"] / 100.0)
    )

    # Degree Hours (Thermal demand proxies)
    df["heating_degree_hour"] = np.maximum(0.0, 18.0 - df["temp_c"])
    df["cooling_degree_hour"] = np.maximum(0.0, df["temp_c"] - 22.0)

    return df



def build_working_dataset():
    print("1. Loading raw parquet datasets...")
    weather_df = io.read("weather_hourly")
    prices_df = io.read("prices_hourly")

    # Standardize timestamp column types
    weather_df["target_ts_utc"] = pd.to_datetime(weather_df["target_ts_utc"], utc=True)
    prices_df["target_ts_utc"] = pd.to_datetime(prices_df["ts_utc"], utc=True)

    print("2. Engineering point-level physical weather features...")
    weather_df = engineer_location_features(weather_df)

    # Numeric columns to pivot per location and aggregate across regions
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

    print("3. Pivoting weather features across locations...")
    # Pivot location-specific weather variables into single wide row per timestamp
    pivoted_df = weather_df.pivot(
        index=["target_ts_utc", "split"], columns="location", values=feature_cols
    )

    # Flatten multi-level column index (e.g. ('temp_c', 'bucuresti') -> 'temp_c_bucuresti')
    pivoted_df.columns = [f"{var}_{loc}" for var, loc in pivoted_df.columns]
    pivoted_df = pivoted_df.reset_index()

    print("4. Calculating regional aggregate features (Romania & Neighbors)...")
    # Spatial macro aggregates across all locations
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
            f"{var}_{loc}"
            for loc in neighbor_locations
            if f"{var}_{loc}" in pivoted_df
        ]

        if ro_cols:
            pivoted_df[f"{var}_ro_mean"] = pivoted_df[ro_cols].mean(axis=1)
            pivoted_df[f"{var}_ro_min"] = pivoted_df[ro_cols].min(axis=1)
            pivoted_df[f"{var}_ro_max"] = pivoted_df[ro_cols].max(axis=1)

        if neigh_cols:
            pivoted_df[f"{var}_neighbors_mean"] = pivoted_df[neigh_cols].mean(axis=1)

    print("5. Joining prices with weather feature panel...")
    # Merge pivoted weather data with national price targets
    working_df = pd.merge(
        prices_df, pivoted_df, on="target_ts_utc", how="inner"
    ).sort_values("target_ts_utc")

    print("6. Adding temporal and cyclical features...")
    ts = working_df["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)

    # Calendar features
    working_df["hour"] = ts.dt.hour
    working_df["dayofweek"] = ts.dt.dayofweek
    working_df["dayofyear"] = ts.dt.dayofyear
    working_df["is_weekend"] = working_df["dayofweek"].isin([5, 6]).astype(int)

    # Cyclical encodings for smooth periodic transitions
    working_df["hour_sin"] = np.sin(2 * np.pi * working_df["hour"] / 24.0)
    working_df["hour_cos"] = np.cos(2 * np.pi * working_df["hour"] / 24.0)
    working_df["dayofweek_sin"] = np.sin(2 * np.pi * working_df["dayofweek"] / 7.0)
    working_df["dayofweek_cos"] = np.cos(2 * np.pi * working_df["dayofweek"] / 7.0)
    working_df["dayofyear_sin"] = np.sin(2 * np.pi * working_df["dayofyear"] / 365.25)
    working_df["dayofyear_cos"] = np.cos(2 * np.pi * working_df["dayofyear"] / 365.25)

    print("7. Generating price lags and rolling memory features...")
    # Assuming price target is 'price_mean' (or 'price'); update if target column differs
    price_col = "price_mean" if "price_mean" in working_df.columns else "price"

    if price_col in working_df.columns:
        # Autoregressive Lags: 24h (day-ahead baseline) & 168h (same hour last week)
        working_df["price_lag_24h"] = working_df[price_col].shift(24)
        working_df["price_lag_48h"] = working_df[price_col].shift(48)
        working_df["price_lag_168h"] = working_df[price_col].shift(168)

        # Rolling Moving Windows
        for window in [3, 6, 24]:
            working_df[f"price_roll_mean_{window}h"] = (
                working_df[price_col].shift(1).rolling(window).mean()
            )
            working_df[f"price_roll_std_{window}h"] = (
                working_df[price_col].shift(1).rolling(window).std()
            )

        # Price momentum / volatility spread
        working_df["price_diff_24h"] = (
            working_df["price_lag_24h"] - working_df["price_lag_48h"]
        )

    print("8. Partitioning into final Train / Validation / Test sets...")
    train_df = (
        working_df[working_df["split"] == "train"]
        .reset_index(drop=True)
    )
    val_df = (
        working_df[working_df["split"] == "validation"]
        .reset_index(drop=True)
    )
    test_df = (
        working_df[working_df["split"] == "test"]
        .reset_index(drop=True)
    )

    print(
        f"\nDataset construction complete:\n"
        f" - Train shape:      {train_df.shape}\n"
        f" - Validation shape: {val_df.shape}\n"
        f" - Test shape:       {test_df.shape}\n"
        f" - Total features:   {len(working_df.columns)}\n"
    )

    return train_df, val_df, test_df, working_df


if __name__ == "__main__":
    train_df, val_df, test_df, working_df = build_working_dataset()