"""Score every model of a task on the same rows, by horizon.

Validation by default. --final scores the test set once and leaves a marker; delete it on purpose
to run again.
"""

import argparse
from collections.abc import Callable
from functools import partial

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.baselines import (
    NAIVE_COLUMN,
    PERSISTENCE_COLUMN,
    Climatology,
    PersistencePrice,
    SeasonalNaivePrice,
    SolarRule,
)
from gridsense.models.calibrate import plot_reliability, reliability_table
from gridsense.models.classify import LABELS, LowPriceClassifier
from gridsense.models.ensemble import PriceEnsemble
from gridsense.models.lear import LEAR
from gridsense.models.metrics import (
    block_slots,
    by_horizon,
    classification_report,
    price_report,
    slot_outcomes,
)
from gridsense.models.price import PriceForecaster
from gridsense.splits import assign_split

HEADLINE = ["n", "mae", "rmae", "mean_pinball", "coverage", "width", "mae_low_price"]
CLASSIFY_HEADLINE = ["n", "base_rate", "pr_auc", "pr_auc_vs_clim", "precision_at_k", "brier"]


def final_marker():
    return config.REPORTS_DIR / "TEST_EVALUATED"


def price_models(
    train: pd.DataFrame, val: pd.DataFrame
) -> dict[str, Callable[[pd.DataFrame], pd.DataFrame]]:
    models = {}
    for baseline in (SeasonalNaivePrice(), PersistencePrice()):
        models[baseline.name] = baseline.fit(train, val).predict
    lear = LEAR().fit(train, val)
    models[lear.name] = lear.predict
    try:
        lgbm, _ = artifacts.load_latest(PriceForecaster.name)
    except FileNotFoundError:
        print(f"no trained {PriceForecaster.name} yet; run `make train TASK=price`")
        return models
    models[lgbm.name] = lgbm.predict
    if lgbm.conformal_offsets:
        models[f"{lgbm.name}_no_conformal"] = partial(lgbm.predict, apply_conformal=False)
    ensemble = PriceEnsemble(lear.predict, lgbm.predict).fit(val.dropna(subset=[NAIVE_COLUMN]))
    print(f"ensemble weight on {lear.name}: {ensemble.weight}")
    models[ensemble.name] = ensemble.predict
    return models


def evaluate_price(train: pd.DataFrame, val: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    # Same rows for every model: drop the few targets without a naive input (DST hours, first week).
    rows = rows.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN])
    reports = []
    for name, predict in price_models(train, val).items():
        scored = rows[["horizon_days", "y_price"]].join(predict(rows))
        report = by_horizon(scored, lambda g: price_report(g["y_price"], g))
        reports.append(report.assign(model=name).reset_index())
    out = pd.concat(reports, ignore_index=True)
    naive_mae = out[out["model"] == SeasonalNaivePrice.name].set_index("horizon")["mae"]
    out["rmae"] = out["mae"] / out["horizon"].map(naive_mae)
    return out


# --- Classification (ML-C) ---


def _cross_fitted(clf: LowPriceClassifier, table: pd.DataFrame) -> pd.DataFrame:
    """Calibrated predictions where each month's calibrator was fitted on the other months.

    Used on validation only: the saved calibrators were fitted on all of val, so scoring them there
    would flatter them. Needs the labels of `table`, which is fine for scoring.
    """
    month = table["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.month.to_numpy()
    return clf.predict_cross_fitted(table, month)


def classify_models(
    train: pd.DataFrame, val: pd.DataFrame, on_val: bool
) -> dict[str, Callable[[pd.DataFrame], pd.DataFrame]]:
    models = {}
    for baseline in (Climatology(), SolarRule()):
        try:
            models[baseline.name] = baseline.fit(train, val).predict
        except ValueError as err:
            print(f"skipping {baseline.name}: {err}")
    try:
        clf, _ = artifacts.load_latest(LowPriceClassifier.name)
    except FileNotFoundError:
        print(f"no trained {LowPriceClassifier.name} yet; run `make train TASK=classify`")
        return models
    if not getattr(clf, "calibrators", None):
        models[clf.name] = clf.predict
        return models
    models[f"{clf.name}_raw"] = partial(clf.predict, apply_calibration=False)
    models[clf.name] = partial(_cross_fitted, clf) if on_val else clf.predict
    return models


def _classify_report(g: pd.DataFrame) -> dict:
    # k = number of positives, i.e. R-precision (as in train.classify_metrics).
    report = classification_report(g["y"], g["p"], k=int(g["y"].sum()))
    return {"n": len(g), "base_rate": float(g["y"].mean())} | report


def evaluate_classify(train: pd.DataFrame, val: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (label, model, horizon); saves a reliability plot per label next to the CSV."""
    on_val = bool(rows.index.isin(val.index).any())
    split_name = "val" if on_val else "test"
    reports, curves, preds = [], {col: {} for col in LABELS}, {}
    for name, predict in classify_models(train, val, on_val).items():
        pred = preds[name] = predict(rows)
        for col, label in LABELS.items():
            scored = pd.DataFrame(
                {"horizon_days": rows["horizon_days"], "y": rows[label].astype(int), "p": pred[col]}
            )
            report = by_horizon(scored, _classify_report)
            reports.append(report.assign(model=name, label=col).reset_index())
            curves[col][name] = reliability_table(scored["p"], scored["y"])
    out = pd.concat(reports, ignore_index=True)

    # PR-AUC relative to climatology at the same label and horizon: 2.0 = twice as good.
    clim = out.loc[out["model"] == Climatology.name, ["label", "horizon", "pr_auc"]]
    out = out.merge(clim.rename(columns={"pr_auc": "_clim"}), on=["label", "horizon"], how="left")
    out["pr_auc_vs_clim"] = out["pr_auc"] / out.pop("_clim")

    for col, model_curves in curves.items():
        path = config.REPORTS_DIR / "eval" / f"reliability_{col}_{split_name}.png"
        title = f"{col} on {split_name} [{config.DATA_MODE}]"
        plot_reliability(model_curves, path, title=title)
    if on_val:
        print(
            f"{LowPriceClassifier.name}: calibration cross-fitted by val month (honest val score)"
        )

    slots = slot_sweep(rows, preds)
    slots.to_csv(config.REPORTS_DIR / "eval" / f"classify_slots_{split_name}.csv", index=False)
    best = slots[(slots["model"] == LowPriceClassifier.name) & (slots["horizon"] == "all")]
    if not best.empty:
        with pd.option_context("display.float_format", "{:.3f}".format):
            print(f"[{config.DATA_MODE}] slots from {LowPriceClassifier.name} on {split_name}")
            print(best.drop(columns=["model", "horizon"]).set_index(["label", "tau"]).to_string())
    return out


# Probability thresholds tau to try when announcing slots, and the price each label's slot must
# clear in every hour to count as a hit.
TAUS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
SLOT_THRESHOLDS = {
    "p_near_zero": config.NEAR_ZERO_THRESHOLD_EUR,
    "p_cheap": config.CHEAP_THRESHOLD_EUR,
}


def slot_sweep(rows: pd.DataFrame, preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Slot metrics per (model, label, tau, horizon), with the block_slots stand-in slot builder.

    hit_rate: share of slots where every hour cleared at or below the label's threshold
    (1 - hit_rate = slots the agent would cancel). cheap_hours_captured: share of the cheap hours
    inside the slot window that fell inside an announced slot.
    """
    prices = rows.drop_duplicates("target_ts_utc").rename(
        columns={"target_ts_utc": "ts_utc", "y_price": "price_mean"}
    )[["ts_utc", "price_mean"]]
    lo, hi = 9, 18  # block_slots' default window
    hour = rows["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.hour
    in_window = (hour >= lo) & (hour < hi)
    horizons = ["all", *sorted(rows["horizon_days"].unique())]

    out = []
    for name, pred in preds.items():
        for col, label in LABELS.items():
            table = rows[["issue_ts", "horizon_days", "target_ts_utc"]].assign(p=pred[col])
            chances = rows.loc[in_window & rows[label].astype(bool), "horizon_days"].value_counts()
            for tau in TAUS:
                slots = block_slots(table, "p", tau, window=(lo, hi))
                outcomes = slot_outcomes(slots, prices, SLOT_THRESHOLDS[col])
                slots = slots.join(outcomes[["cheap_hours", "hit"]])
                for h in horizons:
                    s = slots if h == "all" else slots[slots["horizon_days"] == h]
                    n_chances = chances.sum() if h == "all" else chances.get(h, 0)
                    out.append(
                        {
                            "model": name,
                            "label": col,
                            "tau": tau,
                            "horizon": h,
                            "slots": len(s),
                            "slot_hours": int(s["hours"].sum()),
                            "hit_rate": float(s["hit"].mean()) if len(s) else float("nan"),
                            "cheap_hours_captured": (
                                float(s["cheap_hours"].sum() / n_chances)
                                if n_chances
                                else float("nan")
                            ),
                        }
                    )
    return pd.DataFrame(out)


TASKS = {"price": evaluate_price, "classify": evaluate_classify}
# How main() prints each task's result: index columns and headline metrics.
SUMMARY = {
    "price": (["model", "horizon"], HEADLINE),
    "classify": (["label", "model", "horizon"], CLASSIFY_HEADLINE),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=[*TASKS, "all"], default="all")
    parser.add_argument("--final", action="store_true", help="score the test set (once)")
    args = parser.parse_args(argv)

    split_name = "test" if args.final else "val"
    if args.final and final_marker().exists():
        raise SystemExit(
            f"test set already evaluated ({final_marker()}); delete it on purpose to rerun"
        )

    table = io.read("training_table").dropna(subset=["y_price"])
    split = assign_split(table["target_ts_utc"])
    rows = table[split == split_name]
    if rows.empty:
        raise SystemExit(f"no labelled rows in the {split_name} split")

    out_dir = config.REPORTS_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    for task in TASKS if args.task == "all" else [args.task]:
        result = TASKS[task](table[split == "train"], table[split == "val"], rows)
        result.to_csv(out_dir / f"{task}_{split_name}.csv", index=False)
        index, headline = SUMMARY[task]
        with pd.option_context("display.width", 140, "display.float_format", "{:.3f}".format):
            print(f"[{config.DATA_MODE}] {task} on {split_name}")
            print(result.set_index(index)[headline].to_string())
    if args.final:
        final_marker().write_text(pd.Timestamp.now(tz="UTC").isoformat())


if __name__ == "__main__":
    main()
