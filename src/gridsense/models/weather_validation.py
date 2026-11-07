"""Compare saved weather/no-weather models on validation; solar rule on supported hours.

Run training first. This does not fit on or score test, change schemas, or manufacture
weather for unavailable dates/horizons. Existing no-weather model artifacts are retained.
"""

import hashlib
import json

import joblib
import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.ablate_price import WEATHER_PREFIXES, validation_tables
from gridsense.models.base import feature_columns
from gridsense.models.baselines import (
    NAIVE_COLUMN,
    PERSISTENCE_COLUMN,
    Climatology,
    SolarRule,
)
from gridsense.models.calibrate import plot_reliability, reliability_table
from gridsense.models.classify import LABELS, LowPriceClassifier
from gridsense.models.metrics import by_horizon, classification_report, price_report
from gridsense.models.price import PriceForecaster


def has_weather(features: list[str]) -> bool:
    return any(c.startswith(WEATHER_PREFIXES) for c in features)


def no_weather_model(name: str):
    """Load the newest historical model whose recorded feature list excludes weather."""
    for folder in sorted((config.MODELS_DIR / name).iterdir(), reverse=True):
        metadata_path = folder / "metadata.json"
        if not metadata_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text())
        if metadata.get("features") and not has_weather(metadata["features"]):
            model = joblib.load(folder / "model.joblib")
            if has_weather(model.features):
                raise ValueError("Model artifact disagrees with its metadata")
            return model, folder.name
    raise FileNotFoundError(f"No saved no-weather {name} baseline")


def classification_scores(rows: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
    reports = []
    for column, label in LABELS.items():
        scored = rows[["horizon_days", label]].assign(probability=pred[column])
        if not scored["probability"].between(0, 1).all():
            raise ValueError("Classification probabilities must be finite and in [0,1]")

        def metric(group: pd.DataFrame, label: str = label) -> dict:
            y = group[label].to_numpy(dtype=int)
            return {"n": len(y), **classification_report(
                y, group["probability"].to_numpy(dtype=float), k=int(y.sum()))}

        reports.append(by_horizon(scored, metric).assign(label=label).reset_index())
    return pd.concat(reports, ignore_index=True)


def cross_calibrated_predictions(
    rows: pd.DataFrame, classifier: LowPriceClassifier
) -> pd.DataFrame:
    """Cross-fit each nested step, grouping all horizons of a target month together.

    The underlying model was early-stopped on validation, so this is cross-fitted
    calibration evidence, not independent or forward-only forecasting validation.
    Calibrate P(cheap | near_zero) on eligible rows, never the final p_cheap product.
    """
    groups = rows["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.strftime("%Y-%m")
    if groups.nunique() < 2:
        raise ValueError("Cross-fitted calibration needs at least two target months")
    calibrated = classifier.predict_cross_fitted(rows, groups.to_numpy())
    if not calibrated.index.equals(rows.index):
        raise ValueError("Cross-fitted predictions must align with the scored validation rows")
    if calibrated.p_cheap.gt(calibrated.p_near_zero).any():
        raise ValueError("Cross-fitted classifier probabilities must remain nested")
    return calibrated


def main() -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("This comparison requires real archived weather")
    train, val = validation_tables(io.read("training_table"))
    classifier, classifier_version = artifacts.load_latest(LowPriceClassifier.name)
    price, price_version = artifacts.load_latest(PriceForecaster.name)
    if not has_weather(classifier.features) or not has_weather(price.features):
        raise SystemExit("Train both models with weather first: models.train --task all")
    old_classifier, old_classifier_version = no_weather_model(LowPriceClassifier.name)
    old_price, old_price_version = no_weather_model(PriceForecaster.name)

    models = {"climatology": Climatology().fit(train),
              "lgbm_no_weather": old_classifier, "lgbm_weather": classifier}
    # Newly pulled classifiers apply a val-fitted calibrator by default. Preserve the
    # weather/no-weather RAW comparison; score calibration out-of-month instead of on fit rows.
    predictions = {
        name: (model.predict(val, apply_calibration=False)
               if isinstance(model, LowPriceClassifier) else model.predict(val))
        for name, model in models.items()
    }
    method = getattr(classifier, "calibration", None)
    if method and getattr(classifier, "calibrators", {}):
        predictions[f"lgbm_weather_{method}_crossfit"] = cross_calibrated_predictions(
            val, classifier
        )
    classification = [classification_scores(val, pred).assign(model=name, scope="all_validation")
                      for name, pred in predictions.items()]
    ghi_columns = [c for c in feature_columns(val) if c.startswith("f_ghi_") and c != "f_ghi_mean"]
    if not ghi_columns:
        raise ValueError("No per-location forecast radiation features")
    solar_rows = val[val[ghi_columns].notna().all(axis=1)]
    if solar_rows.empty:
        raise ValueError("No complete archived radiation hours for solar-rule comparison")
    solar = SolarRule().fit(train)
    predictions[solar.name] = solar.predict(val)
    for name, pred in predictions.items():
        classification.append(classification_scores(solar_rows, pred.loc[solar_rows.index]).assign(
            model=name, scope="complete_radiation"
        ))

    price_rows = val.dropna(subset=[NAIVE_COLUMN, PERSISTENCE_COLUMN])
    prices = []
    for name, model in (("lgbm_no_weather", old_price), ("lgbm_weather", price)):
        pred = model.predict(price_rows)
        scored = price_rows[["horizon_days", "y_price"]].join(pred)
        prices.append(by_horizon(scored, lambda g: price_report(g.y_price, g)).assign(
            model=name
        ).reset_index())
    classify_result, price_result = pd.concat(classification), pd.concat(prices)
    availability = val.groupby("horizon_days")[[
        c for c in feature_columns(val) if c.startswith(WEATHER_PREFIXES)]].agg(
        lambda x: float(x.notna().mean())
    )
    out = config.REPORTS_DIR / "eval"
    out.mkdir(parents=True, exist_ok=True)
    for column, label in LABELS.items():
        curves = {
            name: reliability_table(pred[column].to_numpy(dtype=float), val[label].to_numpy(dtype=int))
            for name, pred in predictions.items() if name != SolarRule.name
        }
        for name, curve in curves.items():
            curve.to_csv(out / f"reliability_{column}_{name}.csv", index=False)
        plot_reliability(curves, out / f"reliability_{column}.png",
                         title=f"Validation: {label} (calibration cross-fitted by month)")
    classify_result.to_csv(out / "classify_weather_val.csv", index=False)
    price_result.to_csv(out / "price_weather_val.csv", index=False)
    availability.to_csv(out / "weather_feature_availability.csv")
    manifest = json.loads((config.PROCESSED_DIR / "weather_forecasts_manifest.json").read_text())
    metadata = {
        "run_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "data_mode": config.DATA_MODE,
        "test_evaluated": False, "train_rows": len(train), "val_rows": len(val),
        "calibration_method": method,
        "calibration_score_protocol": "leave-one-target-month-out" if method else None,
        "solar_scored_rows": len(solar_rows), "price_scored_rows": len(price_rows),
        "versions": {"classifier_weather": classifier_version, "price_weather": price_version,
                     "classifier_no_weather": old_classifier_version, "price_no_weather": old_price_version},
        "inputs_sha256": {name: hashlib.sha256((config.PROCESSED_DIR / f"{name}.parquet").read_bytes()).hexdigest()
                          for name in ("training_table", "weather_fc")},
        "weather_manifest": manifest,
        "caveats": ["Validation was also used for early stopping and price calibration.",
                    "Raw classifier scores are used for weather comparisons. Calibrated scores are cross-fitted by target month, not scored on calibration fit rows.",
                    "Month cross-fit uses other months including future months; it is not forward-chaining validation.",
                    "Archived weather uses assumed availability, not original publication timestamps.",
                    "SolarRule.fit treats missing training radiation as not firing; its validation scores exclude missing radiation.",
                    "Precision@k uses the positive count; tied baseline scores may affect ranking.",
                    "Forecast rows across horizons repeat target labels and are not independent."],
    }
    (out / "weather_validation.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(classify_result[classify_result.horizon.eq("all")].set_index(["scope", "model", "label"])[
        ["n", "positives", "pr_auc", "precision_at_k", "brier"]
    ].round(4).to_string())
    print(price_result[price_result.horizon.eq("all")].set_index("model")[[
        "n", "mae", "mean_pinball", "coverage", "width", "mae_low_price"
    ]].round(4).to_string())
    print("Validation weather availability:")
    print(availability.filter(regex="_mean$").round(3).to_string())


if __name__ == "__main__":
    main()