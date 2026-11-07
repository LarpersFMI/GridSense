"""The real models, replayed day by day over a past period: each `forecast` run is one 10:00 issue scored by the
trained models (gridsense.models.predict), each `prices` run one day's real cleared prices. Real data, real models,
a past clock — for the demo, until live inputs exist.

Reads the team's tables in config.PROCESSED_DIR (training_table, prices_hourly) and the latest trained models in
config.MODELS_DIR (`make train`); writes the app's datasets in DATASET_DIR (.env), which must be another folder
(data/replay): appending into the team's own files would corrupt them.

REPLAY_START (a local date, default 2025-04-24) is the first issue day: set from the UI (Pipelines → Replay), the
PipelineRunner passes it. It must be before the test split (config.TEST_START): the test period is evaluated once, by
the ML team, and replayed only after that — ALLOW_TEST_REPLAY=1 (.env) once it has been.
"""
from __future__ import annotations

import os

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.predict import build_predictions
from gridsense.models.price import PriceForecaster
from gridsense.pipelines import Run, pipeline, store
from gridsense.pipelines.demo import DAY
from gridsense.pipelines.store import read

# A spring week in validation with a public holiday (1 May) and many low-price hours.
DEFAULT_START = "2025-04-24"

# Prices before the first issue day, so the charts and the evening context have history from the start.
HISTORY_DAYS = 14


def test_allowed() -> bool:
    """Once the ML team has run the single test evaluation, the demo may replay a test week."""
    return os.environ.get("ALLOW_TEST_REPLAY") == "1"


def check_not_test(day: pd.Timestamp) -> None:
    if day >= config.TEST_START and not test_allowed():
        raise RuntimeError(f"{day.date()} is in the test split (from {config.TEST_START.date()}): the test period is "
                           "evaluated once, by the ML team. Replay it only after that, with ALLOW_TEST_REPLAY=1.")


def replay_start() -> pd.Timestamp:
    """The first issue day, as its local midnight."""
    day = pd.Timestamp(os.environ.get("REPLAY_START", DEFAULT_START), tz=config.LOCAL_TZ)
    check_not_test(day)

    return day


def check_target() -> None:
    """DATASET_DIR is the replay's own folder: not the team's data, and not holding another clock's files."""
    if store.DATASET_DIR == config.PROCESSED_DIR.resolve():
        raise RuntimeError(f"DATASET_DIR is the team's own data folder ({store.DATASET_DIR}): the replay would append into "
                           "their files. Set DATASET_DIR=data/replay in .env.")

    # Files from the synthetic demo (2026 dates, the dummy model) would set the clock in the test split.
    for dataset, column in (("predictions", "issue_ts"), ("prices", "ts_utc")):
        current = read(dataset)

        if current is not None and current[column].max() >= config.TEST_START and not test_allowed():
            raise RuntimeError(f"{store.path(dataset)} runs to {current[column].max().date()}, in the test split: it isn't "
                               "this replay's. Move it aside (or point DATASET_DIR at an empty folder) and run again.")


def local_day(instants: pd.Series) -> pd.Series:
    return instants.dt.tz_convert(config.LOCAL_TZ).dt.normalize()


def next_issue_day() -> pd.Timestamp:
    """The day after the last run in the app's predictions, or the replay's first day."""
    current = read("predictions")

    if current is None:
        return replay_start()

    return local_day(current["issue_ts"]).max() + DAY


# The training table's columns that aren't features: the labels are the real price, unknown at 10:00 on the issue day.
LABELS = ("y_price", "y_near_zero", "y_cheap")


def to_features(rows: pd.DataFrame) -> pd.DataFrame:
    """What the model read for each hour: the key, every feature without its `f_` prefix (as top_features names
    them), and the row's data quality. The labels are left out."""
    key = ["issue_ts", "target_ts_utc", "horizon_days"]

    # f_horizon_days is the key's horizon_days again: kept once.
    features = [column for column in rows.columns if column.startswith("f_") and column.removeprefix("f_") not in key]
    out = rows[[*key, *features]].rename(columns=lambda name: name.removeprefix("f_"))

    if "data_quality" in rows:
        out["data_quality"] = rows["data_quality"].astype("string")

    return out.reset_index(drop=True)


@pipeline("forecast", "Scores the next day's 10:00 issue with the trained models: 7 days ahead, hourly; writes what "
          "the models read (features) next to what they predicted (replay of a past period, real data).",
          outputs=["predictions", "features"], default_cron="0 10 * * *")
def forecast(run: Run) -> None:
    check_target()
    day = next_issue_day()

    check_not_test(day)

    table = io.read("training_table")
    rows = table[local_day(table["issue_ts"]) == day]

    if rows.empty:
        raise RuntimeError(f"No training_table rows issued on {day.date()}: rebuild the features (make features) "
                           "or pick another REPLAY_START.")

    classifier, classifier_version = artifacts.load_latest(LowPriceClassifier.name)
    price, price_version = artifacts.load_latest(PriceForecaster.name)
    version = f"{classifier_version}+{price_version}"

    predictions = build_predictions(rows, classifier, price, version)
    degraded = int((predictions["data_quality"] != "ok").sum())

    print(f"Issue {day.date()} 10:00: {len(predictions)} hours, model {version}"
          + (f", {degraded} hours degraded" if degraded else ""))

    # First what the models read, then what they predicted: the predictions' report sets the Watchdog going.
    run.append("features", to_features(rows), key=["issue_ts", "target_ts_utc"])
    run.append("predictions", predictions, key=["issue_ts", "target_ts_utc"], model_version=version)


@pipeline("prices", "Appends the real cleared prices up to the day after the last forecast — that afternoon's auction "
          f"(replay of a past period). The first run also adds the {HISTORY_DAYS} days before the start.",
          outputs=["prices"], default_cron="15 14 * * *")
def prices(run: Run) -> None:
    check_target()
    history = io.read("prices_hourly")
    current = read("prices")
    issued = read("predictions")

    # The auction for day X clears on X − 1: prices reach the day after the last forecast, never further.
    latest_issue = replay_start() - DAY if issued is None else local_day(issued["issue_ts"]).max()
    end = latest_issue + DAY + DAY

    if current is None:
        start = replay_start() - pd.DateOffset(days=HISTORY_DAYS)
    else:
        start = local_day(current["ts_utc"]).max() + DAY

    if start >= end:
        print(f"Prices already reach {(end - DAY).date()}, the day after the last forecast ({latest_issue.date()}): "
              "run forecast first. Nothing appended.")

        return

    check_not_test(end - DAY)

    rows = history[(history["ts_utc"] >= start.tz_convert("UTC")) & (history["ts_utc"] < end.tz_convert("UTC"))]

    if rows.empty:
        raise RuntimeError(f"No cleared prices from {start.date()} in prices_hourly.")

    days = f"{start.date()}" if end - start <= pd.Timedelta(days=1, hours=1) else f"{start.date()} → {(end - DAY).date()}"
    print(f"Auction prices for {days}: {len(rows)} hours")
    run.append("prices", rows[["ts_utc", "price_mean", "price_min", "price_max"]], key=["ts_utc"])
