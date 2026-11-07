"""Fake predictions table for the agent and demo teams to build against before real models exist.

Probabilities and quantiles come from one latent price curve, so they're mutually consistent:
cheap midday hours on sunny spring/summer weekends, wider uncertainty at longer horizons.
"""

import argparse

import numpy as np
import pandas as pd

from gridsense import config, io

Z90 = 1.2816


def _normal_cdf(x: np.ndarray) -> np.ndarray:
    # Logistic approximation; plenty for fake data and avoids a scipy dependency.
    return 1.0 / (1.0 + np.exp(-1.702 * x))


def _latent_prices(start: pd.Timestamp, end: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq="h", tz=config.LOCAL_TZ)
    local_date = ts.tz_localize(None).normalize()
    hour = ts.hour.to_numpy()
    weekend = (ts.day_of_week >= 5).astype(float)
    season = 0.5 + 0.5 * np.sin(2 * np.pi * (ts.day_of_year.to_numpy() - 80) / 365)
    daylight = np.clip(np.sin(np.pi * (hour - 6) / 14), 0, None)

    days = pd.Index(local_date.unique())
    cloud_by_day = pd.Series(rng.beta(2, 3, len(days)), index=days)
    cloud = cloud_by_day.reindex(local_date).to_numpy()

    solar = daylight * season * (1 - 0.8 * cloud)
    evening = ((hour >= 18) & (hour <= 21)).astype(float)
    price = 115 + 45 * evening - 170 * solar * (1 + 0.35 * weekend) + rng.normal(0, 12, len(ts))
    return pd.DataFrame(
        {"target_ts_utc": ts.tz_convert("UTC"), "target_date": local_date, "price": price, "solar": solar}
    )


def generate(start: pd.Timestamp, end: pd.Timestamp, seed: int = config.RANDOM_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    horizons = list(config.HORIZONS_DAYS)
    targets = _latent_prices(start, end + pd.Timedelta(days=max(horizons) + 1), rng)

    issue_dates = pd.date_range(start.tz_localize(None), end.tz_localize(None), freq="D")
    frames = []
    for h in horizons:
        issues = pd.DataFrame({"issue_date": issue_dates, "target_date": issue_dates + pd.Timedelta(days=h)})
        frames.append(issues.merge(targets, on="target_date").assign(horizon_days=h))
    df = pd.concat(frames, ignore_index=True)

    sigma = 10.0 + 7.0 * df["horizon_days"].to_numpy()
    p50 = df["price"].to_numpy() + rng.normal(0, 0.6 * sigma)
    df["issue_ts"] = (
        (df["issue_date"] + pd.Timedelta(hours=config.ISSUE_HOUR))
        .dt.tz_localize(config.LOCAL_TZ)
        .dt.tz_convert("UTC")
    )
    df["p_near_zero"] = _normal_cdf((config.NEAR_ZERO_THRESHOLD_EUR - p50) / sigma)
    df["p_cheap"] = _normal_cdf((config.CHEAP_THRESHOLD_EUR - p50) / sigma)
    df["price_p10"] = p50 - Z90 * sigma
    df["price_p50"] = p50
    df["price_p90"] = p50 + Z90 * sigma

    # A few rows flagged so the agent's NEEDS_REVIEW path has something to handle.
    df["data_quality"] = np.where(rng.random(len(df)) < 0.02, "missing_weather", "ok")
    df["top_features"] = (
        "f_ghi_national:" + (df["solar"] * 0.3).map("{:+.2f}".format)
        + "; f_is_weekend:" + np.where(df["issue_date"].dt.day_of_week >= 5, "+0.08", "-0.03")
        + "; f_horizon_days:" + (-0.01 * df["horizon_days"]).map("{:+.2f}".format)
    )
    df["model_name"] = "fake"
    df["model_version"] = "fake"
    return df[["issue_ts", "target_ts_utc", "horizon_days", "p_cheap", "p_near_zero", "price_p10",
               "price_p50", "price_p90", "data_quality", "top_features", "model_name", "model_version"]]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=str(config.TEST_START.date()))
    parser.add_argument("--end", default=str(config.TEST_END.date()))
    args = parser.parse_args(argv)
    if config.DATA_MODE != "fake":
        raise SystemExit("refusing to write fake predictions in real mode; set GRIDSENSE_DATA=fake")

    start = pd.Timestamp(args.start, tz=config.LOCAL_TZ)
    end = pd.Timestamp(args.end, tz=config.LOCAL_TZ)
    preds = generate(start, end)
    io.write(preds, "predictions")
    print(f"[fake] wrote {len(preds)} predictions to {config.PROCESSED_DIR}")


if __name__ == "__main__":
    main()
