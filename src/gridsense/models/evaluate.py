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
from gridsense.models.calibrate import cross_fit, plot_reliability, reliability_table
from gridsense.models.classify import LABELS, LowPriceClassifier
from gridsense.models.ensemble import PriceEnsemble
from gridsense.models.lear import LEAR
from gridsense.models.metrics import by_horizon, classification_report, price_report
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
    out = clf.predict(table, apply_calibration=False)
    month = table["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.month.to_numpy()
    for col, label in LABELS.items():
        if col in clf.calibrators:
            out[col] = cross_fit(out[col], table[label].astype(int), month, clf.calibration)
    return out


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
    reports, curves = [], {col: {} for col in LABELS}
    for name, predict in classify_models(train, val, on_val).items():
        pred = predict(rows)
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
    return out


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
