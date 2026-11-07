import pandas as pd

from gridsense.config import (
    PROCESSED_DIR,
    RAW_DIR,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VAL_END,
    VAL_START,
    WEATHER_POINTS,
)
from gridsense.schemas import COUNTRY_CALENDAR

COUNTRY_TIMEZONES = {
    "Romania": "Europe/Bucharest",
    "Hungary": "Europe/Budapest",
    "Bulgaria": "Europe/Sofia",
    "Moldova": "Europe/Chisinau",
}


SPLIT_RANGES_UTC = {
    "Train": (TRAIN_START.tz_convert("UTC"), TRAIN_END.tz_convert("UTC")),
    "Validation": (VAL_START.tz_convert("UTC"), VAL_END.tz_convert("UTC")),
    "Test": (TEST_START.tz_convert("UTC"), TEST_END.tz_convert("UTC")),
}


def build_country_calendar(
    country_name: str, tz_name: str, df_holidays_raw: pd.DataFrame
) -> pd.DataFrame:
    country_holidays = df_holidays_raw[
        df_holidays_raw["country"] == country_name
    ]


    non_working_dates = set(
        country_holidays[
            country_holidays["category"] == "Non-Working (Public)"
        ]["date_utc"]
    )
    working_holiday_dates = set(
        country_holidays[country_holidays["category"] == "Working"]["date_utc"]
    )

    all_utc_ranges = [
        pd.date_range(start_utc, end_utc, freq="1h", tz="UTC")
        for start_utc, end_utc in SPLIT_RANGES_UTC.values()
    ]
    ts_utc_series = pd.DatetimeIndex(
        pd.concat([pd.Series(r) for r in all_utc_ranges]).values, tz="UTC"
    )

    df = pd.DataFrame({"ts_utc": ts_utc_series})

    local_ts = df["ts_utc"].dt.tz_convert(tz_name)
    local_dates = local_ts.dt.strftime("%Y-%m-%d")


    df["is_holiday"] = local_dates.isin(non_working_dates)
    df["is_working_holiday"] = local_dates.isin(working_holiday_dates)

    unique_dates = (
        pd.date_range(
            ts_utc_series.min().date(), ts_utc_series.max().date(), freq="D"
        )
        .strftime("%Y-%m-%d")
        .tolist()
    )

    date_series = pd.to_datetime(unique_dates)
    is_nw = pd.Series(date_series.strftime("%Y-%m-%d").isin(non_working_dates))
    bridge_monday = (
        (date_series.dayofweek == 0)
        & (~is_nw)
        & is_nw.shift(-1, fill_value=False)
    )
    bridge_friday = (
        (date_series.dayofweek == 4)
        & (~is_nw)
        & is_nw.shift(1, fill_value=False)
    )

    bridge_dates = set(date_series[bridge_monday | bridge_friday].strftime("%Y-%m-%d"))
    df["is_bridge_day"] = local_dates.isin(bridge_dates)

    df["is_dst"] = local_ts.apply(lambda ts: bool(ts.dst()))

    day_counts = local_ts.dt.date.value_counts()
    df["day_hours"] = (
        local_ts.dt.date.map(day_counts).fillna(24).astype("int64")
    )

    df["split"] = None
    for split_name, (start_utc, end_utc) in SPLIT_RANGES_UTC.items():
        mask = (df["ts_utc"] >= start_utc) & (df["ts_utc"] <= end_utc)
        df.loc[mask, "split"] = split_name

    df["country"] = country_name

    for col, dtype in COUNTRY_CALENDAR.items():
        df[col] = df[col].astype(dtype)

    return df[list(COUNTRY_CALENDAR)]


def process_calendar_to_parquet() -> None:
    raw_path = RAW_DIR / "holidays.csv"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Raw holiday file not found at {raw_path}. Run holiday extraction script first."
        )

    print(f"Loading raw holidays from {raw_path}...")
    df_holidays_raw = pd.read_csv(raw_path)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    countries = {country for _, _, country in WEATHER_POINTS.values()}

    for country in countries:
        tz_name = COUNTRY_TIMEZONES.get(country)
        if not tz_name:
            print(f"Warning: Timezone mapping missing for {country}. Skipping.")
            continue

        print(f"Generating calendar Parquet for {country} ({tz_name})...")
        df_calendar = build_country_calendar(country, tz_name, df_holidays_raw)

        filename = f"calendar_{country.lower()}.parquet"
        output_path = PROCESSED_DIR / filename

        df_calendar.to_parquet(
            output_path, engine="pyarrow", compression="snappy", index=False
        )

        print(
            f"  -> Successfully generated {filename} ({len(df_calendar):,} rows)"
        )


if __name__ == "__main__":
    process_calendar_to_parquet()