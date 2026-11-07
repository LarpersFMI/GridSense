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
    PersistencePrice,
    SeasonalNaivePrice,
)
from gridsense.models.lear import LEAR
from gridsense.models.metrics import by_horizon, price_report
from gridsense.models.price import PriceForecaster
from gridsense.splits import assign_split

HEADLINE = ["n", "mae", "rmae", "mean_pinball", "coverage", "width", "mae_low_price"]


def final_marker():
    return config.REPORTS_DIR / "TEST_EVALUATED"


def price_models(
    train: pd.DataFrame, val: pd.DataFrame
) -> dict[str, Callable[[pd.DataFrame], pd.DataFrame]]:
    models = {}
    for baseline in (SeasonalNaivePrice(), PersistencePrice(), LEAR()):
        models[baseline.name] = baseline.fit(train, val).predict
    try:
        lgbm, _ = artifacts.load_latest(PriceForecaster.name)
    except FileNotFoundError:
        print(f"no trained {PriceForecaster.name} yet; run `make train TASK=price`")
        return models
    models[lgbm.name] = lgbm.predict
    if lgbm.conformal_offsets:
        models[f"{lgbm.name}_no_conformal"] = partial(lgbm.predict, apply_conformal=False)
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


TASKS = {"price": evaluate_price}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=list(TASKS), default="price")
    parser.add_argument("--final", action="store_true", help="score the test set (once)")
    args = parser.parse_args(argv)

    split_name = "test" if args.final else "val"
    if args.final and final_marker().exists():
        raise SystemExit(f"test set already evaluated ({final_marker()}); delete it on purpose to rerun")

    table = io.read("training_table").dropna(subset=["y_price"])
    split = assign_split(table["target_ts_utc"])
    rows = table[split == split_name]
    if rows.empty:
        raise SystemExit(f"no labelled rows in the {split_name} split")

    result = TASKS[args.task](table[split == "train"], table[split == "val"], rows)
    out_dir = config.REPORTS_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / f"{args.task}_{split_name}.csv", index=False)
    if args.final:
        final_marker().write_text(pd.Timestamp.now(tz="UTC").isoformat())

    with pd.option_context("display.width", 140, "display.float_format", "{:.3f}".format):
        print(f"[{config.DATA_MODE}] {args.task} on {split_name}")
        print(result.set_index(["model", "horizon"])[HEADLINE].to_string())


if __name__ == "__main__":
    main()
