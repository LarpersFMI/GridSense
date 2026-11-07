import argparse

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.classify import LABELS, LowPriceClassifier
from gridsense.models.metrics import by_horizon, classification_report, price_report
from gridsense.models.price import PriceForecaster
from gridsense.splits import assign_split


def load_train_val() -> tuple[pd.DataFrame, pd.DataFrame]:
    table = io.read("training_table").dropna(subset=["y_price"])
    split = assign_split(table["target_ts_utc"])
    return table[split == "train"], table[split == "val"]


def classify_metrics(model: LowPriceClassifier, val: pd.DataFrame) -> dict:
    # Raw LightGBM scores. The calibrators were fitted on val, so scoring the calibrated model on val
    # would flatter it; the _cal_ metrics use cross-fitted calibration (each val month calibrated by
    # the other months) instead.
    pred = model.predict(val, apply_calibration=False)
    val_month = val["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.month.to_numpy()
    pred_cal = model.predict_cross_fitted(val, val_month) if model.calibrators else None
    metrics = {}
    for col, label in LABELS.items():
        y = val[label].astype(int)
        # k = number of positives, i.e. R-precision.
        for key, value in classification_report(y, pred[col], k=int(y.sum())).items():
            metrics[f"{col}_{key}"] = value
        if pred_cal is not None:
            for key, value in classification_report(y, pred_cal[col], k=int(y.sum())).items():
                if key != "positives":
                    metrics[f"{col}_cal_{key}"] = value

        def pr_auc(g: pd.DataFrame, label: str = label) -> dict:
            return {
                "pr_auc": classification_report(g[label], g["_p"], k=int(g[label].sum()))["pr_auc"]
            }

        per_h = by_horizon(val.assign(_p=pred[col]), pr_auc)
        for h, row in per_h.drop(index="all").iterrows():
            metrics[f"{col}_pr_auc_h{h}"] = float(row["pr_auc"])
    return metrics


def price_metrics(model: PriceForecaster, val: pd.DataFrame) -> dict:
    return price_report(val["y_price"], model.predict(val))


TASKS = {
    "classify": (LowPriceClassifier, classify_metrics),
    "price": (PriceForecaster, price_metrics),
}


def train_task(task: str, train: pd.DataFrame, val: pd.DataFrame) -> str:
    model_cls, metrics_fn = TASKS[task]
    model = model_cls().fit(train, val)
    val_metrics = metrics_fn(model, val)
    version = artifacts.save(
        model,
        {
            "task": task,
            "features": model.features,
            "params": model.params,
            "half_life_days": model.half_life_days,
            "best_iterations": model.best_iterations(),
            "train_range": [train["target_ts_utc"].min(), train["target_ts_utc"].max()],
            "val_range": [val["target_ts_utc"].min(), val["target_ts_utc"].max()],
            "val_metrics": val_metrics,
        }
        | (model.metadata() if hasattr(model, "metadata") else {}),
    )
    artifacts.log_experiment(
        {"task": task, "model": model.name, "version": version, "n_features": len(model.features)}
        | {f"val_{k}": v for k, v in val_metrics.items()}
    )
    print(f"[{config.DATA_MODE}] {model.name} {version}: {val_metrics}")
    return version


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train on train, early-stop and score on val.")
    parser.add_argument("--task", choices=[*TASKS, "all"], default="all")
    args = parser.parse_args(argv)

    train, val = load_train_val()
    for task in TASKS if args.task == "all" else [args.task]:
        train_task(task, train, val)


if __name__ == "__main__":
    main()
