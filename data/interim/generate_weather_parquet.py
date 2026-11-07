import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from GridSense.src.gridsense.config import (
    ISSUE_HOUR,
    LOCAL_TZ,
    PROCESSED_DIR,
    RAW_DIR,
)

from GridSense.src.gridsense.schemas import (
    WEATHER_FC,
    CALENDAR
)
def process_raw_weather_to_parquet() -> None:
    raw_path = RAW_DIR / "weather_hourly.csv"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Raw file not found at {raw_path}. Run fetch script first."
        )

    print(f"Loading raw data from {raw_path}...")
    df = pd.read_csv(raw_path)

    column_mapping = {
        "time": "target_ts_utc",
        "temperature_2m": "temp_c",
        "relative_humidity_2m": "relative_humidity_pct",
        "precipitation": "precip_mm",
        "rain": "rain_mm",
        "snowfall": "snowfall_cm",
        "surface_pressure": "pressure_hpa",
        "cloud_cover": "cloud_cover_pct",
        "wind_speed_10m": "wind10_ms",
        "wind_direction_10m": "wind_dir_deg",
    }
    df = df.rename(columns=column_mapping)

    df["target_ts_utc"] = pd.to_datetime(df["target_ts_utc"], utc=True)

    target_local = df["target_ts_utc"].dt.tz_convert(LOCAL_TZ)

    issue_date_local = target_local.apply(
        lambda ts: ts.date()
        if ts.hour >= ISSUE_HOUR
        else (ts - pd.Timedelta(days=1)).date()
    )

    df["issue_date"] = pd.to_datetime(issue_date_local)

    target_date_local = pd.to_datetime(target_local.dt.date)
    df["lead_days"] = (target_date_local - df["issue_date"]).dt.days

    for col, dtype in WEATHER_FC.items():
        if col in df.columns:
            df[col] = df[col].astype(dtype)


    df_out = df[list(WEATHER_FC.keys())].copy()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "weather_hourly.parquet"

    df_out.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)

    print("\n--- Transformation Summary ---")
    print(f"Total Rows: {len(df_out):,}")
    print(f"Schema:\n{df_out.dtypes}")
    print(f"\nParquet file successfully generated at: {output_path}")


if __name__ == "__main__":
    process_raw_weather_to_parquet()