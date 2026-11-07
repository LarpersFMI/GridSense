import time
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

cache_session = requests_cache.CachedSession(".weather_cache", expire_after=-1)

retry_session = retry(cache_session, retries=5, backoff_factor=2)
openmeteo = openmeteo_requests.Client(session=retry_session)

CITIES = {
    "Bucharest": {"lat": 44.4323, "lon": 26.1063},
    "Cluj-Napoca": {"lat": 46.7712, "lon": 23.6236},
    "Iași": {"lat": 47.1585, "lon": 27.6014},
    "Constanța": {"lat": 44.1792, "lon": 28.6498},
    "Timișoara": {"lat": 45.7537, "lon": 21.2257},
    "Brașov": {"lat": 45.6580, "lon": 25.6012},
    "Craiova": {"lat": 44.3302, "lon": 23.7949},
    "Galați": {"lat": 45.4353, "lon": 28.0080},
    "Oradea": {"lat": 47.0465, "lon": 21.9189},
    "Ploiești": {"lat": 44.9367, "lon": 26.0129},
    "Brăila": {"lat": 45.2692, "lon": 27.9576},
    "Arad": {"lat": 46.1866, "lon": 21.3123},
    "Pitești": {"lat": 44.8565, "lon": 24.8692},
    "Bacău": {"lat": 46.5670, "lon": 26.9146},
    "Sibiu": {"lat": 45.7983, "lon": 24.1256},
    "Târgu Mureș": {"lat": 46.5456, "lon": 24.5625},
    "Baia Mare": {"lat": 47.6567, "lon": 23.5850},
    "Buzău": {"lat": 45.1500, "lon": 26.8333},
    "Râmnicu Vâlcea": {"lat": 45.0997, "lon": 24.3693},
    "Satu Mare": {"lat": 47.7900, "lon": 22.8900},
}

API_URL = "https://archive-api.open-meteo.com/v1/archive"

SPLIT_RANGES = {
    "Train": ("2023-01-01", "2025-02-28"),
    "Validation": ("2025-03-01", "2025-09-30"),
    "Test": ("2026-03-01", "2026-10-31"),
}

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


def assign_split_label(df):
    df["time"] = pd.to_datetime(df["time"])
    df["split"] = None

    for split_name, (start_str, end_str) in SPLIT_RANGES.items():
        start_dt = pd.to_datetime(start_str)
        end_dt = pd.to_datetime(end_str) + pd.Timedelta(days=1) - pd.Timedelta(hours=1)

        mask = (df["time"] >= start_dt) & (df["time"] <= end_dt)
        df.loc[mask, "split"] = split_name

    return df.dropna(subset=["split"]).copy()


def fetch_hourly_weather():
    all_dfs = []

    overall_start = "2023-01-01"
    overall_end = "2026-10-31"

    for city_name, coords in CITIES.items():
        print(f"Fetching hourly data for {city_name}...")

        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "start_date": overall_start,
            "end_date": overall_end,
            "hourly": HOURLY_VARIABLES,
            "timezone": "Europe/Bucharest",
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
            ).tz_convert("Europe/Bucharest").tz_localize(None)

            hourly_data = {"time": hourly_time}

            for i, var_name in enumerate(HOURLY_VARIABLES):
                hourly_data[var_name] = hourly.Variables(i).ValuesAsNumpy()

            df_city = pd.DataFrame(data=hourly_data)

            df_city["city"] = city_name
            df_city["latitude"] = coords["lat"]
            df_city["longitude"] = coords["lon"]
            df_city = assign_split_label(df_city)

            all_dfs.append(df_city)

        except Exception as e:
            print(f"Error fetching data for {city_name}: {e}")

        time.sleep(1.0)

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)

        meta_cols = ["city", "split", "latitude", "longitude", "time"]
        final_cols = meta_cols + HOURLY_VARIABLES
        combined_df = combined_df[final_cols]
        return combined_df
    else:
        return pd.DataFrame()


df_hourly = fetch_hourly_weather()

print("\n--- Processing Complete ---")
print("Split Distribution (row counts):")
print(df_hourly["split"].value_counts())

print("\nSample Data (First 5 Rows):")
print(df_hourly.head())
df_hourly.to_csv("romania_hourly_weather_splits_2023_2026.csv", index=False)