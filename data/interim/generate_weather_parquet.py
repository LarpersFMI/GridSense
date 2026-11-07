import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from gridsense import io
from gridsense.config import RAW_DIR
from gridsense.schemas import WEATHER_HOURLY


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
    # The raw fetch uses Open-Meteo's archive API. A clock-based fabricated issue date
    # cannot turn observations into a forecast that existed before a delivery hour.
    for col, dtype in WEATHER_HOURLY.items():
        if col in df.columns:
            df[col] = df[col].astype(dtype)

    df_out = df[list(WEATHER_HOURLY)].copy()
    df_out["source"] = "open_meteo_archive_observed"
    io.write(df_out, "weather_hourly")

    print("\n--- Transformation Summary ---")
    print(f"Total Rows: {len(df_out):,}")
    print(f"Schema:\n{df_out.dtypes}")
    print("\nObserved weather_hourly saved separately; not used as forecast features.")


if __name__ == "__main__":
    process_raw_weather_to_parquet()
