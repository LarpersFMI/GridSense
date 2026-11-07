"""Weekly drift report for the low-price classifier. Owner: ML-C.

    uv run python -m gridsense.models.drift [--start 2025-10-01 --end 2026-02-28] [--tau 0.5]

Scores the latest saved classifier on the training-table rows whose target day lies in
[start, end], joins the realised prices and writes model_drift_rows (schemas.MODEL_DRIFT, complete weeks) to
reports/<mode>/eval/drift_<start>_<end>.csv. The app's pipeline appends the same rows to
DATASET_DIR/model_drift.parquet. That is what the agent's `model_drift` alert
(audience: ML owner) and the dashboard's "Model health" panel read.

The default period is the Oct 2025 - Feb 2026 gap between validation and test: labelled, never
used for fitting, early stopping or calibration, and not the test set. Target days inside the
test split are refused unless --allow-test is given (the test set is evaluated once, together).
"""

import argparse

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.metrics import weekly_drift
from gridsense.schemas import MODEL_DRIFT
from gridsense.splits import assign_split

DEFAULT_START, DEFAULT_END = "2025-10-01", "2026-02-28"


def reference_hit_rates(tau: float) -> dict[str, float]:
    """Validation slot hit rate of the calibrated classifier at `tau`, from `make evaluate`."""
    path = config.REPORTS_DIR / "eval" / "classify_slots_val.csv"
    if not path.is_file():
        print(f"no {path.name}; run `make evaluate TASK=classify` for slot references")
        return {}
    sweep = pd.read_csv(path)
    rows = sweep[
        (sweep["model"] == LowPriceClassifier.name)
        & (sweep["horizon"].astype(str) == "all")
        & (sweep["tau"].round(6) == round(tau, 6))
    ]
    return dict(zip(rows["label"], rows["hit_rate"], strict=True))


def model_drift_rows(
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    tau: float = 0.5,
    reference_hit_rates: dict[str, float] | None = None,
    window_weeks: int = 4,
) -> pd.DataFrame:
    """Rows for DATASET_DIR/model_drift.parquet (schemas.MODEL_DRIFT), for the app's pipeline.

    predictions: the app's predictions history (every run; issue_ts, horizon_days, target_ts_utc,
    p_near_zero, p_cheap, optionally model_version). prices: prices_hourly. Only complete local weeks
    (every hour up to window_end_utc has a cleared price) are returned, so an append keyed on
    (week_start_utc, label) never freezes a half-finished week.
    """
    columns = list(MODEL_DRIFT)
    report = weekly_drift(predictions, prices, tau, reference_hit_rates, window_weeks)
    if report.empty:
        return pd.DataFrame(columns=columns)

    def utc(local_day: pd.Series) -> pd.Series:
        return local_day.dt.tz_localize(config.LOCAL_TZ).dt.tz_convert("UTC")

    out = report.assign(
        week_start_utc=utc(report["week"]),
        window_start_utc=utc(report["window_start"]),
        window_end_utc=utc(report["week"] + pd.Timedelta(days=7)),
        drift=report["calibration_drift"] | report["slot_drift"],
        tau=float(tau),
        window_weeks=int(window_weeks),
    )
    last_hour = prices["ts_utc"].max() + pd.Timedelta(hours=1)
    out = out[out["window_end_utc"] <= last_hour].copy()

    # The model version of the latest run whose forecasts fall in each window.
    versions = predictions.get("model_version", pd.Series("unknown", index=predictions.index))
    runs = predictions.assign(model_version=versions).sort_values("issue_ts")
    out["model_version"] = [
        _latest_version(runs, start, end)
        for start, end in zip(out["window_start_utc"], out["window_end_utc"], strict=True)
    ]
    out = out[columns].reset_index(drop=True)
    for column, dtype in MODEL_DRIFT.items():
        out[column] = out[column].astype(dtype)
    return out


def _latest_version(runs: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> str:
    in_window = runs[(runs["target_ts_utc"] >= start) & (runs["target_ts_utc"] < end)]
    return str(in_window["model_version"].iloc[-1]) if len(in_window) else "unknown"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--start", default=DEFAULT_START, help="first target day (local)")
    parser.add_argument("--end", default=DEFAULT_END, help="last target day (local)")
    parser.add_argument("--tau", type=float, default=0.5, help="slot announcement threshold")
    parser.add_argument("--window-weeks", type=int, default=4)
    parser.add_argument("--allow-test", action="store_true", help="permit test-split target days")
    args = parser.parse_args(argv)

    table = io.read("training_table")
    day = table["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    rows = table[day.between(pd.Timestamp(args.start), pd.Timestamp(args.end))]
    if rows.empty:
        raise SystemExit("no training_table rows with target days in the requested period")
    if not args.allow_test and assign_split(rows["target_ts_utc"]).eq("test").any():
        raise SystemExit("period overlaps the test split; pass --allow-test only when authorised")

    classifier, version = artifacts.load_latest(LowPriceClassifier.name)
    predictions = (
        rows[["issue_ts", "horizon_days", "target_ts_utc"]]
        .join(classifier.predict(rows))
        .assign(model_version=version)
    )
    report = model_drift_rows(
        predictions,
        io.read("prices_hourly"),
        tau=args.tau,
        reference_hit_rates=reference_hit_rates(args.tau),
        window_weeks=args.window_weeks,
    )

    out = config.REPORTS_DIR / "eval" / f"drift_{args.start}_{args.end}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(out, index=False)

    flagged = report[report["drift"]]
    print(
        f"[{config.DATA_MODE}] {LowPriceClassifier.name} {version}: {len(report)} week x label "
        f"rows, {len(flagged)} flagged -> {out}"
    )
    cols = [
        "week_start_utc",
        "label",
        "observed",
        "expected",
        "oe_ratio",
        "z_calibration",
        "slots",
        "slot_hit_rate",
        "z_slots",
        "reason",
    ]
    with pd.option_context(
        "display.width", 200, "display.max_colwidth", 90, "display.float_format", "{:.2f}".format
    ):
        print(report[cols].to_string(index=False))


if __name__ == "__main__":
    main()
