"""Current features vs +RO weather grid vs +RO/HU/BG weather grid on identical validation rows.

Fits every variant from scratch with default settings; never replaces production artifacts,
the training table or the shared weather_fc table. No test evaluation.
"""

import argparse
import hashlib
import json

import pandas as pd

from gridsense import config, io
from gridsense.features.weather_grid import (
    GRID_PREFIX,
    REQUEST_PACE_SECONDS,
    fetch_grid,
    grid_features,
    grid_locations,
    join_grid_features,
)
from gridsense.models.ablate_price import validation_tables
from gridsense.models.base import feature_columns
from gridsense.models.baselines import NAIVE_COLUMN, PERSISTENCE_COLUMN
from gridsense.models.error_analysis import budget_metrics, decision_scores, fit_models
from gridsense.models.regional_validation import price_scores
from gridsense.models.weather_validation import classification_scores

VARIANTS = {"current": (), "ro_grid": ("ro",), "ro_hu_bg_grid": ("ro", "hu", "bg")}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pace-seconds", type=float, default=REQUEST_PACE_SECONDS)
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        raise SystemExit("Weather grid validation requires real archived forecasts")
    train, val = validation_tables(io.read("training_table"))
    start = pd.Timestamp(config.TRAIN_START.date(), tz=config.LOCAL_TZ).tz_convert("UTC")
    end = (pd.Timestamp(config.VAL_END.date()) + pd.Timedelta(days=1)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    grid = fetch_grid(start, end, io.read("weather_fc"), pace_seconds=args.pace_seconds)
    price_index = val.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN]).index
    prices, classes, budgets, availability, runs = [], [], [], [], {}

    for name, countries in VARIANTS.items():
        tr, va = train, val
        if countries:
            features = grid_features(grid, countries)
            tr, va = join_grid_features(train, features), join_grid_features(val, features)
            columns = [c for c in va if c.startswith(GRID_PREFIX)]
            counts = va.groupby("horizon_days")[columns].agg(lambda x: float(x.notna().mean()))
            availability.append(counts.reset_index().assign(variant=name))
        print(f"[{config.DATA_MODE}] fitting {name}: {len(feature_columns(tr))} features", flush=True)
        price_pred, class_pred, info = fit_models(tr, va, price_index)
        rows = va.loc[price_index]
        prices.append(price_scores(rows, price_pred).assign(variant=name))
        classes.extend(classification_scores(va, pred).assign(model=model, variant=name)
                       for model, pred in class_pred.items())
        budgets.append(budget_metrics(rows, decision_scores(rows, price_pred, class_pred)).assign(variant=name))
        runs[name] = {"features": feature_columns(tr), **info}

    prices, classes = pd.concat(prices, ignore_index=True), pd.concat(classes, ignore_index=True)
    budgets = pd.concat(budgets, ignore_index=True)
    out = config.REPORTS_DIR / "eval"
    out.mkdir(parents=True, exist_ok=True)
    prices.to_csv(out / "price_weather_grid_val.csv", index=False)
    classes.to_csv(out / "classify_weather_grid_val.csv", index=False)
    budgets.to_csv(out / "decision_weather_grid_val.csv", index=False)
    pd.concat(availability, ignore_index=True).to_csv(out / "weather_grid_availability.csv", index=False)
    raw_files = grid[["request_sha256", "raw_sha256"]].drop_duplicates()
    metadata = {
        "run_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "data_mode": config.DATA_MODE,
        "test_evaluated": False, "production_artifacts_changed": False, "training_table_changed": False,
        "weather_fc_changed": False, "points": grid_locations(),
        "weighting": "equal per point; no sourced regional capacity weights",
        "weather_rows": len(grid), "raw_files": len(raw_files),
        "raw_files_sha256": hashlib.sha256(
            "".join(sorted(raw_files["raw_sha256"])).encode()).hexdigest(),
        "training_table_sha256": hashlib.sha256(
            (config.PROCESSED_DIR / "training_table.parquet").read_bytes()).hexdigest(),
        "runs": runs,
        "caveats": [
            "Same GFS Previous Runs offsets and assumed 12 h publication buffer as weather_fc; not verified.",
            "Grid aggregates are NaN unless every point in the country is present.",
            "Early stopping, conformal widening and ensemble weight reuse validation.",
            "Added columns change LightGBM feature subsampling; differences of this size need blocked validation.",
            "Forecast rows across horizons repeat target labels and are not independent.",
        ],
    }
    (out / "weather_grid_validation.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n")

    summary = prices[prices.horizon.eq("all")].pivot(index="model", columns="variant", values="mae")
    print("MAE\n" + summary.round(3).to_string())
    low = prices[prices.horizon.eq("all")].pivot(index="model", columns="variant", values="mae_low_price")
    print("MAE <=20\n" + low.round(3).to_string())
    near = classes[classes.horizon.eq("all") & classes.label.eq("y_near_zero")]
    print("PR-AUC near zero\n" + near.pivot(index="model", columns="variant", values="pr_auc").round(4).to_string())
    print(budgets[budgets.horizon.eq("all")].pivot(index="model", columns="variant", values=[
        "precision_at_budget", "slot_hit_rate", "excess_eur_per_mwh"]).round(3).to_string())


if __name__ == "__main__":
    main()
