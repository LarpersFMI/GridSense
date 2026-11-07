"""Fake market, weather and calendar tables that follow schemas.py, for building before real data exists.

Run with GRIDSENSE_DATA=fake so the output goes to data/fake/ and never mixes with real data.
Prices are driven by the weather (so forecasts carry signal), and installed solar grows each
year, so negative hours cluster on sunny spring/summer weekends and become more frequent.
"""

import argparse

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.data.calendar import calendar_for_hours

FAKE_START = "2023-01-01"
FAKE_END = "2026-10-31"
MTU_15MIN_START = pd.Timestamp("2025-10-01", tz=config.LOCAL_TZ)
LOAD_SHAPE = np.array(
    [0.80, 0.77, 0.75, 0.74, 0.75, 0.80, 0.88, 0.96, 1.00, 1.01, 1.01, 1.00,
     0.99, 0.98, 0.98, 0.99, 1.01, 1.05, 1.10, 1.12, 1.10, 1.03, 0.93, 0.85]
)
WIND_MEAN_MS = {"bucuresti": 4.5, "constanta": 8.0, "craiova": 4.5, "timisoara": 4.0}


def _ar1(n: int, phi: float, sigma: float, rng: np.random.Generator) -> np.ndarray:
    eps = rng.normal(0.0, sigma, n)
    out = np.empty(n)
    x = 0.0
    for i in range(n):
        x = phi * x + eps[i]
        out[i] = x
    return out


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _hours(start: str, end: str) -> pd.DatetimeIndex:
    first = pd.Timestamp(start, tz=config.LOCAL_TZ)
    last = pd.Timestamp(f"{end} 23:00", tz=config.LOCAL_TZ)
    return pd.date_range(first, last, freq="h")


def _weather_truth(ts: pd.DatetimeIndex, is_dst: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    date = ts.tz_localize(None).normalize()
    days, day_idx = np.unique(date, return_inverse=True)
    days = pd.DatetimeIndex(days)
    hour = ts.hour.to_numpy() + 0.5
    doy = ts.day_of_year.to_numpy()
    season = np.sin(2 * np.pi * (doy - 80) / 365)

    daylength = 12 + 3.5 * season
    solar_noon = 12.3 + is_dst.astype(float)
    clear_sky = (650 + 250 * season) * np.clip(np.cos(np.pi * (hour - solar_noon) / daylength), 0, None)

    day_season = np.sin(2 * np.pi * (days.day_of_year.to_numpy() - 80) / 365)
    national_cloud = _ar1(len(days), 0.6, 1.0, rng) + (0.1 - 0.9 * day_season)
    temp_anomaly = _ar1(len(days), 0.8, 1.5, rng)

    frames = []
    for loc in config.WEATHER_POINTS:
        cloud = _sigmoid(national_cloud + rng.normal(0, 0.5, len(days)))[day_idx]
        # Newly configured locations use an uncalibrated fake inland wind mean.
        wind = WIND_MEAN_MS.get(loc, 4.5) - 1.0 * season + _ar1(len(ts), 0.97, 0.6, rng)
        temp = (
            11 + 12 * np.sin(2 * np.pi * (doy - 110) / 365)
            + 4 * np.sin(2 * np.pi * (hour - 9) / 24)
            + temp_anomaly[day_idx]
        )
        frames.append(
            pd.DataFrame(
                {
                    "ts_utc": ts.tz_convert("UTC"),
                    "date": date,
                    "location": loc,
                    "clear_sky": clear_sky,
                    "cloud": cloud,
                    "ghi": clear_sky * (1 - 0.75 * cloud),
                    "wind": np.clip(wind, 0, None),
                    "temp": temp,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _weather_forecasts(truth: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    days = pd.DatetimeIndex(truth["date"].unique()).sort_values()
    pairs = pd.concat(
        [
            pd.DataFrame({"issue_date": days, "lead_days": lead, "date": days + pd.Timedelta(days=lead)})
            for lead in config.HORIZONS_DAYS
        ],
        ignore_index=True,
    )
    fc = pairs.merge(truth, on="date")

    # One error draw per (issue, lead, location): forecasts miss whole days, not single hours.
    key = fc.groupby(["issue_date", "lead_days", "location"]).ngroup().to_numpy()
    n_keys = key.max() + 1
    lead = fc["lead_days"].to_numpy()
    cloud = np.clip(fc["cloud"].to_numpy() + 0.07 * lead * rng.normal(size=n_keys)[key], 0, 1)
    wind = fc["wind"].to_numpy() + 0.5 * lead * rng.normal(size=n_keys)[key] + rng.normal(0, 0.5, len(fc))
    temp = fc["temp"].to_numpy() + 0.4 * lead * rng.normal(size=n_keys)[key] + rng.normal(0, 0.3, len(fc))
    return pd.DataFrame(
        {
            "issue_date": fc["issue_date"],
            "target_ts_utc": fc["ts_utc"],
            "lead_days": fc["lead_days"].astype("int64"),
            "location": fc["location"],
            "ghi_wm2": fc["clear_sky"].to_numpy() * (1 - 0.75 * cloud),
            "cloud_cover_pct": 100 * cloud,
            "wind100_ms": np.clip(wind, 0, None),
            "temp_c": temp,
        }
    )


def _grid_and_prices(
    ts: pd.DatetimeIndex, truth: pd.DataFrame, is_holiday: np.ndarray, rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame]:
    wide = truth.pivot(index="ts_utc", columns="location", values=["ghi", "wind", "temp"])
    ghi = wide["ghi"].mean(axis=1).to_numpy()
    wind_coast = wide["wind"]["constanta"].to_numpy()
    temp = wide["temp"]["bucuresti"].to_numpy()

    ts_utc = ts.tz_convert("UTC")
    years = ((ts_utc - pd.Timestamp(FAKE_START, tz="UTC")) / pd.Timedelta(days=365.25)).to_numpy()
    hour = ts.hour.to_numpy()
    doy = ts.day_of_year.to_numpy()
    weekend = ts.day_of_week.to_numpy() >= 5

    solar = (1500 + 1050 * years) * ghi / 1000 * 0.85
    wind = 2000 * np.clip((wind_coast / 13) ** 3, 0, 1)
    load = (
        (6200 + 45 * np.clip(16 - temp, 0, None) + 60 * np.clip(temp - 24, 0, None))
        * LOAD_SHAPE[hour]
        * np.where(weekend, 0.9, 1.0)
        * np.where(is_holiday, 0.85, 1.0)
    )
    residual = load - solar - wind

    level = 95 + 35 * np.exp(-years / 0.8) + 10 * np.cos(2 * np.pi * (doy - 15) / 365)
    evening = (hour >= 18) & (hour <= 21)
    price = (
        level
        + 0.02 * (residual - 5500)
        - 0.06 * np.clip(3000 - residual, 0, None)
        + 30 * evening
        + _ar1(len(ts), 0.9, 7.0, rng)
    )
    price += (evening & (rng.random(len(ts)) < 0.003)) * rng.exponential(250, len(ts))
    price = np.clip(price, -150, None)
    spread = np.where(ts >= MTU_15MIN_START, np.abs(rng.normal(0, 4, len(ts))), 0.0)

    grid = pd.DataFrame(
        {"ts_utc": ts_utc, "load_actual_mw": load, "solar_actual_mw": solar, "wind_actual_mw": wind}
    )
    prices = pd.DataFrame(
        {"ts_utc": ts_utc, "price_mean": price, "price_min": price - spread, "price_max": price + spread}
    )
    return grid, prices


def generate(
    start: str = FAKE_START, end: str = FAKE_END, seed: int = config.RANDOM_SEED
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    ts = _hours(start, end)
    calendar = calendar_for_hours(ts)
    truth = _weather_truth(ts, calendar["is_dst"].to_numpy(), rng)
    weather_fc = _weather_forecasts(truth, rng)
    grid, prices = _grid_and_prices(ts, truth, calendar["is_holiday"].to_numpy(), rng)
    return {"prices_hourly": prices, "grid_hourly": grid, "weather_fc": weather_fc, "calendar": calendar}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=FAKE_START)
    parser.add_argument("--end", default=FAKE_END)
    args = parser.parse_args(argv)
    if config.DATA_MODE != "fake":
        raise SystemExit("refusing to write fake market data in real mode; set GRIDSENSE_DATA=fake")

    tables = generate(args.start, args.end)
    for name, df in tables.items():
        io.write(df, name)
        print(f"[fake] {name}: {len(df):,} rows")

    prices = tables["prices_hourly"]
    year = prices["ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.year
    share = pd.DataFrame(
        {
            "neg_share": (prices["price_mean"] <= config.CHEAP_THRESHOLD_EUR).groupby(year).mean(),
            "near_zero_share": (prices["price_mean"] <= config.NEAR_ZERO_THRESHOLD_EUR).groupby(year).mean(),
        }
    )
    print(share.round(3).to_string())


if __name__ == "__main__":
    main()
