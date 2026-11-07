from datetime import datetime
import holidays
import pandas as pd

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

COUNTRY_MAP = {
    "Romania": "RO",
    "Hungary": "HU",
    "Bulgaria": "BG",
    "Moldova": "MD",
}

SPLIT_RANGES_UTC = {
    "Train": (TRAIN_START.tz_convert("UTC"), TRAIN_END.tz_convert("UTC")),
    "Validation": (VAL_START.tz_convert("UTC"), VAL_END.tz_convert("UTC")),
    "Test": (TEST_START.tz_convert("UTC"), TEST_END.tz_convert("UTC")),
}


YEARS = list(range(TRAIN_START.year, TEST_END.year + 1))


def assign_split_label(dt_utc: pd.Timestamp):
    for split_name, (start_utc, end_utc) in SPLIT_RANGES_UTC.items():
        if start_utc <= dt_utc <= end_utc:
            return split_name
    return None


def extract_holidays() -> pd.DataFrame:
    records = []

    countries = set(country for _, _, country in WEATHER_POINTS.values())

    for country_name in countries:
        country_code = COUNTRY_MAP.get(country_name)
        if not country_code:
            continue

        country_public = holidays.country_holidays(
            country_code, years=YEARS, categories="public"
        )

        try:
            country_all = holidays.country_holidays(
                country_code,
                years=YEARS,
                categories=("public", "unofficial", "observance"),
            )
        except (ValueError, KeyError):
            country_all = holidays.country_holidays(country_code, years=YEARS)

        for date_obj, name in sorted(country_all.items()):
            dt_utc = pd.Timestamp(date_obj).tz_localize("UTC")
            split = assign_split_label(dt_utc)

            if split is not None:
                is_non_working = date_obj in country_public

                records.append(
                    {
                        "date_utc": dt_utc.strftime("%Y-%m-%d"),
                        "country": country_name,
                        "country_code": country_code,
                        "holiday_name": name,
                        "category": (
                            "Non-Working (Public)"
                            if is_non_working
                            else "Working"
                        ),
                        "split": split,
                        "day_of_week": dt_utc.strftime("%A"),
                        "falls_on_weekend": dt_utc.weekday() in (5, 6),
                    }
                )

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(
            subset=["date_utc", "country_code", "holiday_name"]
        ).reset_index(drop=True)

    return df


if __name__ == "__main__":
    df_holidays = extract_holidays()

    print("\n--- Summary by Country and Category ---")
    print(df_holidays.groupby(["country", "category"]).size())

    print("\n--- Summary by Split ---")
    print(df_holidays["split"].value_counts())

    print("\n--- Sample Output ---")
    print(df_holidays.head(10))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_DIR / "holidays.csv"
    df_holidays.to_csv(output_path, index=False)
    print(f"\nHolidays successfully saved to: {output_path}")