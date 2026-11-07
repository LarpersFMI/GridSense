"""Weekly drift report for the low-price classifier. Owner: ML-C.

    uv run python -m gridsense.models.drift [--start 2025-10-01 --end 2026-02-28] [--tau 0.5]

Scores the latest saved classifier on the training-table rows whose target day lies in
[start, end], joins the realised prices and writes metrics.weekly_drift to
reports/<mode>/eval/drift_<start>_<end>.csv. That is what the agent's `model_drift` alert
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
    predictions = rows[["issue_ts", "horizon_days", "target_ts_utc"]].join(classifier.predict(rows))
    report = weekly_drift(
        predictions,
        io.read("prices_hourly"),
        tau=args.tau,
        reference_hit_rates=reference_hit_rates(args.tau),
        window_weeks=args.window_weeks,
    ).assign(model_version=version, tau=args.tau)

    out = config.REPORTS_DIR / "eval" / f"drift_{args.start}_{args.end}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(out, index=False)

    flagged = report[report["calibration_drift"] | report["slot_drift"]]
    print(
        f"[{config.DATA_MODE}] {LowPriceClassifier.name} {version}: {len(report)} week x label "
        f"rows, {len(flagged)} flagged -> {out}"
    )
    cols = [
        "week",
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
