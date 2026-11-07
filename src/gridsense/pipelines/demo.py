"""Stand-ins until the real ones arrive (ENTSO-E prices, the model's daily run): they append the next day of the
SYNTHETIC dummy (gridsense.synthetic), and past its end the last day again, a day later. Everything they write is
FAKE. The real ones, replaying past days through the trained models, are in replay.py.
"""
from __future__ import annotations

import pandas as pd

from gridsense.config import LOCAL_TZ, SYNTHETIC_DIR
from gridsense.pipelines import Run, pipeline
from gridsense.pipelines.store import read

MODEL_NAME = "dummy"
MODEL_VERSION = "dummy-0"


# A calendar day in Bucharest: 23 or 25 hours when the clocks change. `+ pd.Timedelta(days=1)` would be 24 hours.
DAY = pd.DateOffset(days=1)


def next_local_day(after: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The local day after the one `after` falls on, as [start, end) in UTC."""
    day = after.tz_convert(LOCAL_TZ).normalize() + DAY

    return day.tz_convert("UTC"), (day + DAY).tz_convert("UTC")


def a_local_day_later(instants: pd.Series) -> pd.Series:
    """The same local time, a day later: 10:00 stays 10:00 across a clock change."""
    return (instants.dt.tz_convert(LOCAL_TZ) + DAY).dt.tz_convert("UTC")


@pipeline("prices-dummy", "Appends the next day's cleared prices from the synthetic dummy (FAKE).",
          outputs=["prices"], default_cron="15 14 * * *")
def prices(run: Run) -> None:
    current = read("prices")
    dummy = pd.read_parquet(SYNTHETIC_DIR / "prices_hourly_dummy.parquet")
    latest = (dummy if current is None else current)["ts_utc"].max()
    start, end = next_local_day(latest)

    rows = dummy[(dummy["ts_utc"] >= start) & (dummy["ts_utc"] < end)]

    if rows.empty:
        # The day's hours (23, 24 or 25), with the last hours' prices.
        index = pd.date_range(start, end, freq="h", inclusive="left")
        last = (current if current is not None else dummy).sort_values("ts_utc").tail(len(index))
        rows = last.assign(ts_utc=index[-len(last):])
        print(f"The dummy ends before {start.tz_convert(LOCAL_TZ).date()}: repeating the last day's prices")

    print(f"Auction for {start.tz_convert(LOCAL_TZ).date()}: {len(rows)} hours")
    run.append("prices", rows, key=["ts_utc"])


@pipeline("forecast-dummy", "Appends the day's model run from the synthetic dummy: 7 days ahead, hourly (FAKE).",
          outputs=["predictions"], default_cron="0 10 * * *")
def forecast(run: Run) -> None:
    current = read("predictions")
    dummy = pd.read_parquet(SYNTHETIC_DIR / "predictions_dummy.parquet")
    latest = (dummy if current is None else current)["issue_ts"].max()

    later = dummy[dummy["issue_ts"] > latest]

    if later.empty:
        last = (current if current is not None else dummy)
        rows = last[last["issue_ts"] == latest].assign(
            issue_ts=lambda f: a_local_day_later(f["issue_ts"]),
            target_ts_utc=lambda f: a_local_day_later(f["target_ts_utc"]),
        )
        print(f"The dummy ends at {latest.isoformat()}: repeating its last run a day later")
    else:
        rows = later[later["issue_ts"] == later["issue_ts"].min()]

    rows = rows.assign(model_name=MODEL_NAME, model_version=MODEL_VERSION)
    print(f"Run issued {rows['issue_ts'].iloc[0].isoformat()}: {len(rows)} hours")
    run.append("predictions", rows, key=["issue_ts", "target_ts_utc"], model_version=MODEL_VERSION)
