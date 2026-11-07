"""Compare price feature groups on validation only, without changing the training table.

The current variant also refreshes the standard price artifact and price_val.csv.
Week-ahead results are exploratory: historical publication times were re-stamped, and
the feature builder uses a calendar availability assumption rather than vintage joins.
"""

import hashlib
import json

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.base import PRICE_COLUMNS, feature_columns
from gridsense.models.baselines import (
    NAIVE_COLUMN,
    PERSISTENCE_COLUMN,
    PersistencePrice,
    SeasonalNaivePrice,
)
from gridsense.models.ensemble import PriceEnsemble
from gridsense.models.evaluate import HEADLINE
from gridsense.models.lear import LEAR
from gridsense.models.metrics import by_horizon, price_report
from gridsense.models.price import PriceForecaster
from gridsense.models.train import train_task
from gridsense.splits import assign_split

GRID_FEATURES = ("f_load_mean_dm1", "f_solar_max_dm1", "f_wind_mean_dm1")
WEEK_FEATURES = ("f_load_fc_min", "f_load_fc_max")
WEATHER_PREFIXES = ("f_ghi_", "f_cloud_", "f_wind100_", "f_temp_")


def validation_tables(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    table = table.dropna(subset=["y_price"])
    split = assign_split(table["target_ts_utc"])
    train, val = table[split == "train"], table[split == "val"]
    if train.empty or val.empty:
        raise ValueError("A labelled train split and validation split are required")
    return train, val


def feature_variants(table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Only remove columns; keep exactly the same rows and labels in every variant."""
    missing = [c for c in WEEK_FEATURES if c not in table]
    if missing:
        raise ValueError(f"Rebuild features with week-ahead data first; missing {missing}")
    weather = [c for c in table if c.startswith(WEATHER_PREFIXES)]
    without_weather = table.drop(columns=weather)
    variants = {
        "prices_calendar": without_weather.drop(columns=[*GRID_FEATURES, *WEEK_FEATURES], errors="ignore"),
        "lagged_load": without_weather.drop(columns=list(WEEK_FEATURES)),
        "lagged_load_week_ahead": without_weather.copy(),
    }
    if weather:
        variants["lagged_load_week_ahead_weather"] = table.copy()
    return variants


def main() -> None:
    train, val = validation_tables(io.read("training_table"))
    train_variants, val_variants = feature_variants(train), feature_variants(val)
    current_variant = list(train_variants)[-1]
    # Match the standard evaluation harness: all models score the same complete baseline rows.
    score_index = val.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN]).index
    if score_index.empty:
        raise ValueError("No validation rows have both baseline inputs")
    reports, runs, availability = [], {}, []
    for split_name, table in (("train", train), ("val", val)):
        for feature in (*GRID_FEATURES, *WEEK_FEATURES):
            if feature in table:
                part = table.groupby("horizon_days")[feature].agg(
                    rows="size", non_null="count"
                ).reset_index()
                availability.append(
                    part.assign(
                        split=split_name,
                        feature=feature,
                        availability=part["non_null"] / part["rows"],
                    )
                )

    for variant, tr in train_variants.items():
        va = val_variants[variant]
        rows = va.loc[score_index]
        print(f"[{config.DATA_MODE}] fitting {variant}: {len(feature_columns(tr))} features", flush=True)
        if variant == current_variant:
            version = train_task("price", tr, va)
            lgbm, _ = artifacts.load_latest(PriceForecaster.name)
        else:
            version = None
            lgbm = PriceForecaster().fit(tr, va)
        lear = LEAR().fit(tr, va)
        predictions = {
            baseline.name: baseline.fit(tr, va).predict(rows)
            for baseline in (SeasonalNaivePrice(), PersistencePrice())
        }
        predictions[lear.name] = lear.predict(rows)
        predictions[lgbm.name] = lgbm.predict(rows)
        predictions[f"{lgbm.name}_no_conformal"] = lgbm.predict(rows, apply_conformal=False)
        # Cache predictions: weight tuning and reporting must use these exact scored rows.
        ensemble = PriceEnsemble(
            lambda _, pred=predictions[lear.name]: pred,
            lambda _, pred=predictions[lgbm.name]: pred,
        )
        ensemble.fit(rows)
        predictions[ensemble.name] = ensemble.predict(rows)
        active = [c for c in feature_columns(tr) if tr[c].notna().any()]
        runs[variant] = {
            "features": feature_columns(tr), "active_features": active,
            "best_iterations": lgbm.best_iterations(), "lear_weight": ensemble.weight,
            "artifact_version": version,
        }
        for name, pred in predictions.items():
            if pred[list(PRICE_COLUMNS)].isna().any().any():
                raise ValueError(f"Missing price predictions for {variant}/{name}")
            scored = rows[["horizon_days", "y_price"]].join(pred)
            report = by_horizon(scored, lambda g: price_report(g["y_price"], g))
            reports.append(report.assign(model=name, variant=variant).reset_index())
        headline = pd.concat(reports).query("variant == @variant and horizon == 'all'")
        print(headline.set_index("model")[["mae", "mean_pinball", "coverage", "mae_low_price"]].round(3))

    result = pd.concat(reports, ignore_index=True)
    naive = result[result["model"] == SeasonalNaivePrice.name].set_index(["variant", "horizon"])["mae"]
    result["rmae"] = result["mae"] / pd.MultiIndex.from_frame(result[["variant", "horizon"]]).map(naive)
    out = config.REPORTS_DIR / "eval"
    out.mkdir(parents=True, exist_ok=True)
    result.to_csv(out / "price_ablation_val.csv", index=False)
    result[result["variant"] == current_variant].drop(columns="variant").to_csv(
        out / "price_val.csv", index=False
    )
    pd.concat(availability, ignore_index=True).to_csv(out / "price_feature_availability.csv", index=False)
    inputs = {
        name: hashlib.sha256((config.PROCESSED_DIR / f"{name}.parquet").read_bytes()).hexdigest()
        for name in ("training_table", "prices_hourly", "grid_hourly", "load_fc_week_ahead", "weather_fc")
        if (config.PROCESSED_DIR / f"{name}.parquet").exists()
    }
    metadata = {
        "data_mode": config.DATA_MODE, "run_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "train_range": [str(config.TRAIN_START), str(config.TRAIN_END)],
        "val_range": [str(config.VAL_START), str(config.VAL_END)],
        "train_rows": len(train), "val_rows": len(val), "scored_val_rows": len(score_index),
        "scored_unique_target_hours": val.loc[score_index, "target_ts_utc"].nunique(),
        "test_evaluated": False, "input_sha256": inputs, "runs": runs,
        "caveats": [
            "Week-ahead availability is assumed; historical publication times were re-stamped.",
            "Latest forecast revisions are not necessarily the vintage available at issue time.",
            "Early stopping, intervals and ensemble weights reuse validation; these are tuning scores.",
            "All-empty grid features are preserved to match the standard training pipeline.",
            "Feature ablation also changes LightGBM's random feature subsampling.",
            "Weather offsets use an assumed publication buffer, not verified historical release times.",
        ],
    }
    (out / "price_ablation_val.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(result.query("horizon == 'all'").set_index(["variant", "model"])[HEADLINE].round(3))


if __name__ == "__main__":
    main()