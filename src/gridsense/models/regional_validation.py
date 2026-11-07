"""Current versus +regional features on identical validation rows; no test evaluation.

Fit both variants from scratch with default settings. Save experiment artifacts in
a separate namespace; never replace the normal production model artifacts or training table.
"""

import hashlib
import json

import joblib
import pandas as pd

from gridsense import config, io
from gridsense.features.regional import (
    REGIONAL_COLUMNS,
    join_regional_features,
    read_regional_table,
)
from gridsense.models import artifacts
from gridsense.models.ablate_price import validation_tables
from gridsense.models.base import PRICE_COLUMNS, feature_columns
from gridsense.models.baselines import (
    NAIVE_COLUMN,
    PERSISTENCE_COLUMN,
    Climatology,
    PersistencePrice,
    SeasonalNaivePrice,
)
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.ensemble import PriceEnsemble
from gridsense.models.lear import LEAR
from gridsense.models.metrics import by_horizon, price_report
from gridsense.models.price import PriceForecaster
from gridsense.models.weather_validation import classification_scores


def variant_tables(train: pd.DataFrame, val: pd.DataFrame, regional: pd.DataFrame):
    """Remove regional columns for the control; both experiments use the same rows/labels."""
    base_train = train.drop(columns=list(REGIONAL_COLUMNS), errors="ignore")
    base_val = val.drop(columns=list(REGIONAL_COLUMNS), errors="ignore")
    added_train, missing_train = join_regional_features(base_train, regional)
    added_val, missing_val = join_regional_features(base_val, regional)
    return {"current": (base_train, base_val), "regional": (added_train, added_val)}, {
        "train": missing_train, "val": missing_val,
    }


def price_scores(rows: pd.DataFrame, predictions: dict[str, pd.DataFrame]) -> pd.DataFrame:
    reports = []
    for name, pred in predictions.items():
        if not pred.index.equals(rows.index) or pred[list(PRICE_COLUMNS)].isna().any().any():
            raise ValueError(f"Price predictions must be complete and aligned: {name}")
        scored = rows[["horizon_days", "y_price"]].join(pred)
        reports.append(by_horizon(scored, lambda g: price_report(g.y_price, g)).assign(
            model=name
        ).reset_index())
    out = pd.concat(reports, ignore_index=True)
    naive = out[out.model.eq(SeasonalNaivePrice.name)].set_index("horizon")["mae"]
    out["rmae"] = out["mae"] / out["horizon"].map(naive)
    return out


def main() -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("Regional validation requires real data")
    source = io.read("training_table")
    train, val = validation_tables(source)
    # No test or unassigned labels are passed to any fitting, calibration, or scoring function.
    regional, provenance = read_regional_table()
    variants, missing = variant_tables(train, val, regional)
    price_index = val.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN]).index
    if price_index.empty:
        raise ValueError("No validation rows have the baseline inputs")
    version = artifacts.new_version()
    model_dir = config.MODELS_DIR / "regional_experiment" / version
    model_dir.mkdir(parents=True)
    price_reports, class_reports, runs, availability, importance = [], [], {}, [], []

    for name, (tr, va) in variants.items():
        print(f"[{config.DATA_MODE}] fitting {name}: {len(feature_columns(tr))} features", flush=True)
        price = PriceForecaster().fit(tr, va)
        lear = LEAR().fit(tr, va)
        rows = va.loc[price_index]
        predictions = {
            m.name: m.fit(tr, va).predict(rows)
            for m in (SeasonalNaivePrice(), PersistencePrice())
        }
        predictions[lear.name], predictions[price.name] = lear.predict(rows), price.predict(rows)
        ensemble = PriceEnsemble(
            lambda _, pred=predictions[lear.name]: pred,
            lambda _, pred=predictions[price.name]: pred,
        ).fit(rows)
        predictions[ensemble.name] = ensemble.predict(rows)
        price_report_rows = price_scores(rows, predictions).assign(variant=name)
        price_reports.append(price_report_rows)
        print(price_report_rows[price_report_rows.horizon.eq("all")].set_index("model")[[
            "mae", "mean_pinball", "coverage", "mae_low_price"
        ]].round(3).to_string(), flush=True)

        classifier = LowPriceClassifier().fit(tr, va)
        raw = classifier.predict(va, apply_calibration=False)
        cal = classifier.predict_cross_fitted(
            va, va.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.strftime("%Y-%m").to_numpy())
        class_predictions = {
            "climatology": Climatology().fit(tr).predict(va),
            "lgbm_raw": raw, "lgbm_platt_crossfit": cal,
        }
        for model, pred in class_predictions.items():
            class_reports.append(classification_scores(va, pred).assign(model=model, variant=name))
        quality = {
            "raw_probability_order_violations": int(raw.p_cheap.gt(raw.p_near_zero).sum()),
            "crossfit_probability_order_violations": int(cal.p_cheap.gt(cal.p_near_zero).sum()),
        }
        runs[name] = {
            "features": feature_columns(tr),
            "active_train_features": [c for c in feature_columns(tr) if tr[c].notna().any()],
            "lear_weight": ensemble.weight,
            "price_params": price.params, "classifier_params": classifier.params,
            "price_best_iterations": price.best_iterations(),
            "classifier_best_iterations": classifier.best_iterations(),
            "probability_quality": quality,
        }
        # Deliberately separate from lgbm_quantile/lgbm_classifier so load_latest is unchanged.
        joblib.dump({"price": price, "lear": lear, "classifier": classifier,
                     "lear_weight": ensemble.weight}, model_dir / f"{name}.joblib")
        if name == "regional":
            gain = pd.Series(price.models[0.5].booster_.feature_importance(importance_type="gain"),
                             index=price.features)
            importance.append(pd.DataFrame({"feature": gain.index, "gain": gain.to_numpy(),
                                            "gain_share": gain.to_numpy() / gain.sum()}))
            for split_name, table in (("train", tr), ("val", va)):
                for c in REGIONAL_COLUMNS:
                    counts = table.groupby("horizon_days")[c].agg(rows="size", non_null="count").reset_index()
                    availability.append(counts.assign(split=split_name, feature=c,
                                                      availability=counts.non_null / counts.rows))

    prices, classes = pd.concat(price_reports, ignore_index=True), pd.concat(class_reports, ignore_index=True)
    out = config.REPORTS_DIR / "eval"
    out.mkdir(parents=True, exist_ok=True)
    prices.to_csv(out / "price_regional_val.csv", index=False)
    classes.to_csv(out / "classify_regional_val.csv", index=False)
    pd.concat(availability, ignore_index=True).to_csv(out / "regional_feature_availability.csv", index=False)
    pd.concat(importance, ignore_index=True).sort_values("gain", ascending=False).to_csv(
        out / "regional_price_importance.csv", index=False
    )
    metadata = {
        "data_mode": config.DATA_MODE, "run_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "artifact_version": version, "train_rows": len(train), "val_rows": len(val),
        "price_scored_rows": len(price_index), "unique_val_hours": val.target_ts_utc.nunique(),
        "train_range": [str(config.TRAIN_START), str(config.TRAIN_END)],
        "val_range": [str(config.VAL_START), str(config.VAL_END)],
        "test_evaluated": False, "production_artifacts_changed": False,
        "training_table_changed": False, "unmatched_regional_keys": missing,
        "input_sha256": {n: hashlib.sha256((config.PROCESSED_DIR / f"{n}.parquet").read_bytes()).hexdigest()
                         for n in ("training_table", "regional_market_features")},
        "regional_provenance": provenance, "runs": runs,
        "caveats": [
            "All models use the same train/validation rows and default settings; added columns also change feature subsampling.",
            "Base-model early stopping and price intervals reuse validation; these are tuning scores.",
            "Classifier calibration is cross-fitted by target month, not forward-chaining validation.",
            "Source price vintages and old Power Statistics load publication times are not independently verified.",
            "Weather and week-ahead publication/revision assumptions remain as documented in ml_handoff.",
            "Independent binary labels may violate p_cheap <= p_near_zero; counts are reported, not clipped.",
            "Permutation/counterfactual tests prove lag logic, not original source-vintage availability.",
            "Repeated horizons share target labels and are not independent observations.",
        ],
    }
    (out / "regional_validation.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("Price validation:")
    print(prices[prices.horizon.eq("all")].set_index(["variant", "model"])[[
        "mae", "rmae", "mean_pinball", "coverage", "mae_low_price"
    ]].round(4).to_string())
    print("Classification validation:")
    print(classes[classes.horizon.eq("all")].set_index(["variant", "model", "label"])[[
        "pr_auc", "precision_at_k", "brier"
    ]].round(4).to_string())


if __name__ == "__main__":
    main()