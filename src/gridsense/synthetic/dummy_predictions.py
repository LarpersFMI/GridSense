"""SYNTHETIC dummy predictions + cleared prices, so the agent and dashboard can be built
before the real model exists.

    uv run python -m gridsense.synthetic.dummy_predictions

Writes (data/ is gitignored):
    data/synthetic/predictions_dummy.parquet    schema = schemas.PREDICTIONS
    data/synthetic/prices_hourly_dummy.parquet  schema = schemas.PRICES_HOURLY ("cleared" auction prices)
    data/synthetic/predictions_dummy_sample.csv one issue day, for eyeballing

Everything here is FAKE. It is NOT model output and must never be reported as a result.
It's built so that the agent can be tested realistically:

* A hidden "true" world: daily sunshine (seasonal, with cloudy spells), wind, weekends,
  Romanian holidays, evening peak. Cleared prices come from it, so midday prices go negative
  on sunny spring/summer weekends and evening prices spike.
* Forecasts issued every day at ISSUE_HOUR for D+1..D+7: the model sees sunshine/wind with an
  error that grows with the horizon, so P10-P90 widens and probabilities flatten further out.
  Probabilities are roughly calibrated against the cleared prices by construction.
* Edge cases for the agent:
    - ~4% of issue days have a degraded weather feed (data_quality="degraded": wider, flatter)
    - ~1% of issue days fail input checks (data_quality="failed": climatology-like output)
    - 2026-05-16 (Saturday): forecast sunny from D-7..D-2, actually cloudy -> a slot the agent
      announces early and must cancel after the auction
    - DST days (2026-03-29 has 23 hours, 2026-10-25 has 25) because targets are built in local time
"""
from __future__ import annotations

import math

import holidays
import numpy as np
import pandas as pd

from gridsense import config, schemas

OUT_DIR = config.SYNTHETIC_DIR
TZ = config.LOCAL_TZ
MODEL_VERSION = "dummy-0"

# hidden world parameters
BASE = 125.0          # €/MWh baseline
EVENING = 110.0       # extra at 18:00-21:59
MORNING = 25.0        # extra at 07:00-08:59
SOLAR = 135.0         # max price drop at full sun, noon
WIND = 28.0           # price drop per unit wind
WEEKEND_SOLAR_MULT = 1.40
WEEKEND_DEMAND = -20.0
NOISE_SD = 20.0
FLOOR = -100.0

CANCEL_DAY = pd.Timestamp("2026-05-16").date()   # forecast sunny, actually cloudy


def _norm_cdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def _hidden_world(days: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    """One row per local day: sunshine in [0,1], wind index, day type."""
    doy = days.dayofyear.to_numpy()
    season = np.clip(np.sin(np.pi * (doy - 50) / 230), 0, 1)        # ~0 in Feb, 1 in late June
    clouds = np.zeros(len(days))
    for i in range(1, len(days)):                                    # AR(1) cloudy spells
        clouds[i] = 0.65 * clouds[i - 1] + rng.normal(0, 0.45)
    clear = np.clip(0.62 + 0.33 * np.tanh(-clouds), 0.05, 1.0)
    sun = (0.35 + 0.65 * season) * clear
    wind = rng.gamma(2.0, 0.35, len(days))
    ro = holidays.RO(years=sorted(set(days.year)))
    hol = np.array([d.date() in ro for d in days])
    wkend = np.asarray(days.dayofweek >= 5) | hol
    df = pd.DataFrame({"sun": sun, "wind": wind, "season": season, "off_day": wkend, "holiday": hol},
                      index=days.date)
    df.loc[CANCEL_DAY, "sun"] = 0.15 * (0.35 + 0.65 * df.loc[CANCEL_DAY, "season"])
    return df


def _solar_shape(hour: np.ndarray, season: float) -> np.ndarray:
    rise, set_ = 6.8 - 1.6 * season, 19.2 + 1.6 * season
    x = (hour + 0.5 - rise) / (set_ - rise)
    return np.where((x > 0) & (x < 1), np.sin(np.pi * np.clip(x, 0, 1)), 0.0)


def _price_mean(hour, sun, wind, season, off_day):
    g = _solar_shape(hour, season)
    mult = WEEKEND_SOLAR_MULT if off_day else 1.0
    evening = ((hour >= 18) & (hour <= 21)).astype(float)
    morning = ((hour >= 7) & (hour <= 8)).astype(float)
    m = (BASE + EVENING * evening + MORNING * morning + (WEEKEND_DEMAND if off_day else 0.0)
         - SOLAR * sun * g * mult - WIND * wind * (1.0 - 0.4 * evening))
    return m, g, mult


def _local_hours(day) -> pd.DatetimeIndex:
    start = pd.Timestamp(day).tz_localize(TZ)
    end = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(TZ)     # 23 / 25 h on DST days
    return pd.date_range(start, end, freq="h", inclusive="left")


def build(issue_start="2026-02-22", issue_end="2026-10-31", seed=config.RANDOM_SEED):
    rng = np.random.default_rng(seed)
    last_target = pd.Timestamp(issue_end) + pd.Timedelta(days=max(config.HORIZONS_DAYS))
    days = pd.date_range(pd.Timestamp(issue_start), last_target, freq="D")
    world = _hidden_world(days, rng)

    # cleared ("actual") prices
    price_rows = []
    for d, w in world.iterrows():
        hours = _local_hours(d)
        m, _, _ = _price_mean(hours.hour.to_numpy(), w.sun, w.wind, w.season, w.off_day)
        p = np.maximum(m + rng.normal(0, NOISE_SD, len(m)), FLOOR)
        spread = np.abs(rng.normal(0, 8, len(m)))
        price_rows.append(pd.DataFrame({"ts_utc": hours.tz_convert("UTC"), "price_mean": p,
                                        "price_min": p - spread, "price_max": p + spread * 1.2}))
    prices = pd.concat(price_rows, ignore_index=True)

    # forecasts
    issue_days = pd.date_range(issue_start, issue_end, freq="D")
    q = {0.1: -1.2816, 0.5: 0.0, 0.9: 1.2816}
    rows = []
    for issue in issue_days:
        issue_ts = (pd.Timestamp(issue).tz_localize(TZ) + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_convert("UTC")
        u = rng.random()
        feed = "failed" if u < 0.01 else "degraded" if u < 0.05 else "ok"
        for h in config.HORIZONS_DAYS:
            day = (issue + pd.Timedelta(days=h)).date()
            w = world.loc[day]
            sd_sun, sd_wind = 0.08 + 0.045 * h, 0.15 + 0.08 * h
            sun_hat = float(np.clip(w.sun + rng.normal(0, sd_sun), 0, 1))
            wind_hat = float(max(w.wind + rng.normal(0, sd_wind), 0))
            if day == CANCEL_DAY and h >= 2:        # the forecast miss
                sun_hat = 0.85 * (0.35 + 0.65 * w.season)
            if day == CANCEL_DAY and h == 1:
                sun_hat = 0.55 * (0.35 + 0.65 * w.season)
            dq = feed if (feed == "ok" or h >= rng.integers(1, 4)) else "ok"

            hours = _local_hours(day)
            hr = hours.hour.to_numpy()
            m, g, mult = _price_mean(hr, sun_hat, wind_hat, w.season, w.off_day)
            m = m + rng.normal(0, 4, len(m))         # per-hour model wiggle
            sd = np.sqrt(NOISE_SD**2 + (SOLAR * g * mult * sd_sun) ** 2 + (WIND * sd_wind) ** 2)
            if dq == "degraded":                    # no fresh weather: shrink to seasonal mean, widen
                m_clim, _, _ = _price_mean(hr, 0.6 * (0.35 + 0.65 * w.season), 0.7, w.season, w.off_day)
                m, sd = 0.5 * m + 0.5 * m_clim, sd * 1.6
            elif dq == "failed":
                m, _, _ = _price_mean(hr, 0.6 * (0.35 + 0.65 * w.season), 0.7, w.season, w.off_day)
                sd = sd * 2.2
            p_nz = _norm_cdf((config.NEAR_ZERO_THRESHOLD_EUR - m) / sd)
            p_ch = _norm_cdf((config.CHEAP_THRESHOLD_EUR - m) / sd)
            quant = {k: np.maximum(m + z * sd, FLOOR) for k, z in q.items()}

            contrib = {
                "ghi_forecast": -SOLAR * sun_hat * g * mult,
                "off_day": (SOLAR * sun_hat * g * (mult - 1) - WEEKEND_DEMAND) * -1 if w.off_day else 0 * g,
                "evening_peak": EVENING * ((hr >= 18) & (hr <= 21)),
                "wind_dobrogea": -WIND * wind_hat * np.ones_like(g),
                "horizon_days": np.full_like(g, 2.0 * h),
            }
            names = list(contrib)
            mat = np.vstack([np.asarray(contrib[n], dtype=float) for n in names]).T / -400.0  # + = towards cheap
            tops = []
            for row in mat:
                idx = np.argsort(-np.abs(row))[:3]
                tops.append("; ".join(f"{names[i]}:{row[i]:+.2f}" for i in idx))
            rows.append(pd.DataFrame({
                "issue_ts": issue_ts, "target_ts_utc": hours.tz_convert("UTC"), "horizon_days": h,
                "p_cheap": p_ch, "p_near_zero": p_nz,
                "price_p10": quant[0.1], "price_p50": quant[0.5], "price_p90": quant[0.9],
                "data_quality": dq, "top_features": tops,
            }))
    pred = pd.concat(rows, ignore_index=True)
    pred["horizon_days"] = pred["horizon_days"].astype("int64")
    for c in ["issue_ts", "target_ts_utc"]:
        pred[c] = pred[c].astype("datetime64[ns, UTC]")
    prices["ts_utc"] = prices["ts_utc"].astype("datetime64[ns, UTC]")
    for c in ["data_quality", "top_features"]:
        pred[c] = pred[c].astype("string")
    for c in ["p_cheap", "p_near_zero"]:
        pred[c] = pred[c].round(4)
    for c in ["price_p10", "price_p50", "price_p90"]:
        pred[c] = pred[c].round(1)
    prices[["price_mean", "price_min", "price_max"]] = prices[["price_mean", "price_min", "price_max"]].round(2)
    return pred, prices


def check_schema(df: pd.DataFrame, schema: dict) -> None:
    assert list(df.columns) == list(schema), (list(df.columns), list(schema))
    for col, dtype in schema.items():
        got = str(df[col].dtype)
        assert got == dtype or (dtype == "datetime64[ns, UTC]" and got.startswith("datetime64") and "UTC" in got), (col, got, dtype)


def main() -> None:
    pred, prices = build()
    check_schema(pred, schemas.PREDICTIONS)
    check_schema(prices, schemas.PRICES_HOURLY)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pred.to_parquet(OUT_DIR / "predictions_dummy.parquet", index=False)
    prices.to_parquet(OUT_DIR / "prices_hourly_dummy.parquet", index=False)
    sample = pred[pred.issue_ts == pred.issue_ts.unique()[74]].copy()
    sample.insert(1, "target_local", sample.target_ts_utc.dt.tz_convert(TZ).dt.strftime("%a %Y-%m-%d %H:%M"))
    sample.to_csv(OUT_DIR / "predictions_dummy_sample.csv", index=False)
    print(f"predictions: {len(pred):,} rows, {pred.issue_ts.nunique()} issue days -> {OUT_DIR}")
    print(f"prices:      {len(prices):,} rows")


if __name__ == "__main__":
    main()
