"""Replays the SYNTHETIC dummy week as if it were happening now, for the demo: the agent can't wait a day per run.

    uv run python -m gridsense.replay --from 2026-05-13 --to 2026-05-15 --create-triggers --step

The files start with what was known at local midnight on --from: the runs issued before it, and the prices of every
day whose auction had cleared (up to --from itself). Then, for each day, in order:

    10:00  the day's run: its rows are appended to predictions.parquet, then reported (POST /internal/runs)
    14:00  the auction for the next day: its prices are appended to prices_hourly.parquet, then reported

with --pause seconds between steps, or, with --step, one step each time you press Enter (for a live demo). Each trigger finds its own new rows past its watermark, so the Watchdog sees the
week arrive the way it would live.

It writes into DATASET_DIR (.env), which the server and the Watchdog read: point it at a folder of its own
(DATASET_DIR=data/replay), never at data/processed. --create-triggers saves the five demo triggers (T1-T5) once the
starting files are written, so they read only what the replay appends.

Everything here is FAKE (see gridsense.synthetic.dummy_predictions); none of it is a result.
"""
from __future__ import annotations

import argparse
import os
import secrets
import time
import uuid
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from gridsense.config import ISSUE_HOUR, LOCAL_TZ, ROOT, SYNTHETIC_DIR
from gridsense.report_dataset_updated import post, report_dataset_updated, report_run

load_dotenv(ROOT / ".env")

MODEL_VERSION = "dummy-0"

PREDICTIONS_FILE = "predictions.parquet"
PRICES_FILE = "prices_hourly.parquet"


def uuid7() -> str:
    """A UUIDv7, as the TypeScript side makes ids (Foundations.Id): 48-bit milliseconds, then random."""
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    value = (value & ~(0xF << 76)) | (0x7 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)

    return str(uuid.UUID(int=value))


def demo_triggers() -> list[dict]:
    """T1-T5, as an admin would write them in the editor (Trigger.Schema)."""
    on_predictions = {"type": "dataset", "dataset": "predictions", "incrementalColumn": "issue_ts"}
    on_prices = {"type": "dataset", "dataset": "prices", "incrementalColumn": "ts_utc"}

    return [
        {
            "name": "Zero-cost window",
            "description": "Daytime hours likely to clear near zero: candidate free hours to announce.",
            "on": on_predictions,
            "conditions": [
                {"dataset": "predictions", "column": "p_near_zero", "operator": ">=", "value": 0.75},
                {"dataset": "predictions", "column": "local_hour", "operator": "between", "value": [9, 17]},
                {"dataset": "predictions", "column": "data_quality", "operator": "==", "value": "ok"},
            ],
            "grouping": {"type": "window", "minHours": 2, "maxHours": 6},
            "cooldownMinutes": 1440,
        },
        {
            "name": "Forecast dropped",
            "description": "A daytime hour's chance of near-zero fell sharply since the last run: an announced slot may not hold.",
            "on": on_predictions,
            "conditions": [
                {"dataset": "predictions", "column": "p_near_zero_change", "operator": "<=", "value": -0.15},
                {"dataset": "predictions", "column": "local_hour", "operator": "between", "value": [9, 17]},
            ],
            "grouping": {"type": "window", "minHours": 1, "maxHours": 6},
            "cooldownMinutes": 360,
        },
        {
            "name": "Forecast miss",
            "description": "Hours we called near zero that cleared above 20 EUR/MWh at the auction.",
            "on": on_prices,
            "conditions": [
                {"dataset": "predictions", "column": "p_near_zero", "operator": ">=", "value": 0.7},
                {"dataset": "prices", "column": "price_mean", "operator": ">", "value": 20},
            ],
            "grouping": {"type": "hour"},
            "cooldownMinutes": 0,
        },
        {
            "name": "Degraded data",
            "description": "A run's inputs were degraded or failed checks: its forecast is less sure.",
            "on": on_predictions,
            "conditions": [
                {"dataset": "predictions", "column": "data_quality", "operator": "in", "value": ["degraded", "failed"]},
            ],
            "grouping": {"type": "run"},
            "cooldownMinutes": 720,
        },
        {
            "name": "Weekly report",
            "description": "Monday morning: what was announced last week, what the auction confirmed, what was missed.",
            "on": {"type": "schedule", "cron": "0 8 * * MON"},
            "conditions": [],
            "grouping": {"type": "run"},
            "cooldownMinutes": 0,
        },
    ]


def local_midnight(day: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(day.date()).tz_localize(LOCAL_TZ).tz_convert("UTC")


def write(frame: pd.DataFrame, path: Path) -> None:
    """Whole, then renamed into place: the Watchdog never reads a half-written file."""
    partial = path.with_suffix(".partial")
    frame.to_parquet(partial, index=False)
    os.replace(partial, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="first", required=True, help="first local day, e.g. 2026-05-13")
    parser.add_argument("--to", dest="last", required=True, help="last local day, e.g. 2026-05-15")
    parser.add_argument("--pause", type=float, default=5, help="seconds between steps")
    parser.add_argument("--step", action="store_true", help="wait for Enter before each step instead of --pause")
    parser.add_argument("--create-triggers", action="store_true", help="save T1-T5 before the first step")
    args = parser.parse_args()

    target = (ROOT / os.environ.get("DATASET_DIR", "data/replay")).resolve()

    if target == (ROOT / "data/processed").resolve():
        raise SystemExit("DATASET_DIR is data/processed: point it at a folder of its own (DATASET_DIR=data/replay)")

    target.mkdir(parents=True, exist_ok=True)

    predictions = pd.read_parquet(SYNTHETIC_DIR / "predictions_dummy.parquet")
    prices = pd.read_parquet(SYNTHETIC_DIR / "prices_hourly_dummy.parquet")

    days = pd.date_range(args.first, args.last, freq="D")
    start = local_midnight(days[0])

    known_predictions = predictions[predictions["issue_ts"] < start]
    known_prices = prices[prices["ts_utc"] < local_midnight(days[0] + pd.Timedelta(days=1))]

    write(known_predictions, target / PREDICTIONS_FILE)
    write(known_prices, target / PRICES_FILE)

    print(f"Starting at {days[0].date()} 00:00: {known_predictions['issue_ts'].nunique()} runs, "
          f"prices up to {days[0].date()} — in {target}")

    if args.create_triggers:
        for trigger in demo_triggers():
            post("/api/triggers", {"id": uuid7(), "enabled": True, "match": "all", **trigger})
            print(f"  saved trigger: {trigger['name']}")

    def wait(next_step: str) -> None:
        if args.step:
            input(f"  Enter: {next_step} ")
        else:
            time.sleep(args.pause)

    for day in days:
        issue_ts = (pd.Timestamp(day.date()) + pd.Timedelta(hours=ISSUE_HOUR)).tz_localize(LOCAL_TZ).tz_convert("UTC")
        run = predictions[predictions["issue_ts"] == issue_ts]

        if run.empty:
            print(f"{day.date()} 10:00  no run in the dummy for {issue_ts.isoformat()}, skipped")
        else:
            wait(f"{day.date()} 10:00, the day's run")
            known_predictions = pd.concat([known_predictions, run], ignore_index=True)
            write(known_predictions, target / PREDICTIONS_FILE)
            report_run(target / PREDICTIONS_FILE, MODEL_VERSION, issue_ts)
            print(f"{day.date()} 10:00  run issued {issue_ts.isoformat()}: {len(run)} hours appended and reported")

        next_day = day + pd.Timedelta(days=1)
        cleared = prices[(prices["ts_utc"] >= local_midnight(next_day))
                         & (prices["ts_utc"] < local_midnight(next_day + pd.Timedelta(days=1)))]

        wait(f"{day.date()} 14:00, the auction for {next_day.date()}")
        known_prices = pd.concat([known_prices, cleared], ignore_index=True)
        write(known_prices, target / PRICES_FILE)
        report_dataset_updated("prices")
        print(f"{day.date()} 14:00  auction for {next_day.date()}: {len(cleared)} hours appended and reported")


if __name__ == "__main__":
    main()
