import json
import pandas as pd
from gridsense import io
from gridsense.features.feature_augmentation import build_working_dataset, engineer_location_features
from src.gridsense.config import LOCAL_TZ, REPORTS_DIR, WEATHER_POINTS


def load_ranked_features() -> list[str]:
    """Loads the ordered feature importance list from JSON artifact."""
    ranking_path = REPORTS_DIR / "feature_importance.json"
    if not ranking_path.exists():
        raise FileNotFoundError(
            f"Feature ranking file not found at {ranking_path}. "
            "Run `src/features/rank_features.py` first to generate ranking."
        )

    with open(ranking_path, "r", encoding="utf-8") as f:
        ranked_features = json.load(f)

    return ranked_features


def create_augmented_dataset(nr_features: int = 30) -> pd.DataFrame:
    """Extracts top `nr_features` along with non-training metadata columns and saves to Parquet."""
    print("1. Loading full working dataset...")
    train_df, val_df, test_df, working_df = build_working_dataset()

    ranked_features = load_ranked_features()
    selected_features = ranked_features[:nr_features]

    # Non-training metadata columns to preserve
    metadata_cols = [
        col for col in working_df.columns
        if col not in ranked_features
    ]

    print(
        f"2. Filtering dataset to Top {nr_features} features + {len(metadata_cols)} metadata columns..."
    )
    final_cols = metadata_cols + selected_features

    # Keep only existing columns
    final_cols = [c for c in final_cols if c in working_df.columns]
    augmented_df = working_df[final_cols].copy()

    print("3. Exporting dataset via io.write('weather_hourly_augmented')...")
    print(augmented_df.columns)
    io.write(augmented_df, "weather_hourly_augmented")
    print("   Dataset successfully exported.")

    return augmented_df

def compute_features_for_new_data(
        df_new_weather: pd.DataFrame,
        df_new_prices: pd.DataFrame = None,
        nr_features: int = 30,
) -> pd.DataFrame:
    """Computes feature transformations for fresh input data and keeps the top `nr_features`."""
    print(f"1. Processing feature transformations for new data ({len(df_new_weather)} rows)...")

    # Ensure timestamp column format
    df_weather = df_new_weather.copy()
    df_weather["target_ts_utc"] = pd.to_datetime(df_weather["target_ts_utc"], utc=True)

    # 1. Apply point-level physical feature engineering
    df_engineered = engineer_location_features(df_weather)

    # 2. Pivot per location
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

    available_cols = [c for c in feature_cols if c in df_engineered.columns]

    pivoted_df = df_engineered.pivot(
        index=["target_ts_utc"], columns="location", values=available_cols
    )
    pivoted_df.columns = [f"{var}_{loc}" for var, loc in pivoted_df.columns]
    pivoted_df = pivoted_df.reset_index()

    # 3. Macro regional aggregates
    ro_locations = [loc for loc, (_, _, country) in WEATHER_POINTS.items() if country == "Romania"]
    neigh_locations = [loc for loc, (_, _, country) in WEATHER_POINTS.items() if country != "Romania"]

    for var in ["temp_c", "wind10_ms", "wind_power_density", "solar_proxy_wm2"]:
        ro_cols = [f"{var}_{loc}" for loc in ro_locations if f"{var}_{loc}" in pivoted_df]
        neigh_cols = [f"{var}_{loc}" for loc in neigh_locations if f"{var}_{loc}" in pivoted_df]

        if ro_cols:
            pivoted_df[f"{var}_ro_mean"] = pivoted_df[ro_cols].mean(axis=1)
            pivoted_df[f"{var}_ro_min"] = pivoted_df[ro_cols].min(axis=1)
            pivoted_df[f"{var}_ro_max"] = pivoted_df[ro_cols].max(axis=1)

        if neigh_cols:
            pivoted_df[f"{var}_neighbors_mean"] = pivoted_df[neigh_cols].mean(axis=1)

    # 4. Join prices if provided
    if df_new_prices is not None:
        df_prices = df_new_prices.copy()
        df_prices["target_ts_utc"] = pd.to_datetime(df_prices["target_ts_utc"], utc=True)
        working_df = pd.merge(df_prices, pivoted_df, on="target_ts_utc", how="inner").sort_values("target_ts_utc")
    else:
        working_df = pivoted_df.sort_values("target_ts_utc")

    # 5. Temporal Features
    ts = working_df["target_ts_utc"].dt.tz_convert(LOCAL_TZ)
    working_df["hour"] = ts.dt.hour
    working_df["dayofweek"] = ts.dt.dayofweek
    working_df["dayofyear"] = ts.dt.dayofyear
    working_df["is_weekend"] = working_df["dayofweek"].isin([5, 6]).astype(int)

    working_df["hour_sin"] = pd.np.sin(2 * pd.np.pi * working_df["hour"] / 24.0) if hasattr(pd,
                                                                                            'np') else import_numpy_sin(
        working_df["hour"], 24.0)
    # ... standard math sin/cos encodings ...

    # 6. Load top N features
    ranked_features = load_ranked_features()
    selected_features = [f for f in ranked_features[:nr_features] if f in working_df.columns]

    # Non-feature metadata columns to preserve
    metadata_cols = [c for c in working_df.columns if c not in ranked_features]

    return working_df[metadata_cols + selected_features].copy()


def import_numpy_sin(series: pd.Series, period: float) -> pd.Series:
    import numpy as np
    return np.sin(2 * np.pi * series / period)


if __name__ == "__main__":
    # Generate and write weather_hourly_augmented with top 30 features
    df_augmented = create_augmented_dataset(nr_features=30)