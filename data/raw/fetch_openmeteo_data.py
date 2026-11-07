import time
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
from GridSense.src.gridsense.config import (
    LOCAL_TZ,
    RAW_DIR,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VAL_END,
    VAL_START,
    WEATHER_POINTS,
)

cache_session = requests_cache.CachedSession(".weather_cache", expire_after=-1)
retry_session = retry(cache_session, retries=5, backoff_factor=2)
openmeteo = openmeteo_requests.Client(session=retry_session)

API_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "snowfall",
    "surface_pressure",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
]


SPLIT_RANGES_UTC = {
    "train": (TRAIN_START.tz_convert("UTC"), TRAIN_END.tz_convert("UTC")),
    "validation": (VAL_START.tz_convert("UTC"), VAL_END.tz_convert("UTC")),
    "test": (TEST_START.tz_convert("UTC"), TEST_END.tz_convert("UTC")),
}


def assign_split_label(df: pd.DataFrame) -> pd.DataFrame:
    df["split"] = None

    for split_name, (start_utc, end_utc) in SPLIT_RANGES_UTC.items():
        mask = (df["time"] >= start_utc) & (df["time"] <= end_utc)
        df.loc[mask, "split"] = split_name

    return df.dropna(subset=["split"]).copy()


def fetch_hourly_weather() -> pd.DataFrame:
    all_dfs = []

    overall_start = TRAIN_START.strftime("%Y-%m-%d")
    overall_end = TEST_END.strftime("%Y-%m-%d")

    for point_name, (lat, lon, country) in WEATHER_POINTS.items():
        print(f"Fetching hourly UTC data for {point_name}...")

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": overall_start,
            "end_date": overall_end,
            "hourly": HOURLY_VARIABLES,
            "timezone": "UTC",
        }

        try:
            responses = openmeteo.weather_api(API_URL, params=params)
            response = responses[0]

            hourly = response.Hourly()

            hourly_time = pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left",
            )

            hourly_data = {"time": hourly_time}

            for i, var_name in enumerate(HOURLY_VARIABLES):
                hourly_data[var_name] = hourly.Variables(i).ValuesAsNumpy()

            df_point = pd.DataFrame(data=hourly_data)

            df_point["location"] = point_name
            df_point["country"] = country
            df_point["latitude"] = lat
            df_point["longitude"] = lon

            df_point = assign_split_label(df_point)

            all_dfs.append(df_point)

        except Exception as e:
            print(f"Error fetching data for {point_name}: {e}")

        time.sleep(1.0)

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)

        meta_cols = ["location","country", "split", "latitude", "longitude", "time"]
        final_cols = meta_cols + HOURLY_VARIABLES
        combined_df = combined_df[final_cols]
        return combined_df
    else:
        return pd.DataFrame()


if __name__ == "__main__":
    df_hourly = fetch_hourly_weather()

    print("\n--- Extraction Summary ---")
    print("Split Distribution (row counts):")
    print(df_hourly["split"].value_counts())

    print("\nSample Data (First 5 Rows):")
    print(df_hourly.head())

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_DIR / "weather_hourly.csv"
    df_hourly.to_csv(output_path, index=False)
    print(f"\nDataset successfully saved to: {output_path}")