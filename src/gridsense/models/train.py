import argparse

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.classify import LABELS, LowPriceClassifier
from gridsense.models.metrics import classification_report, quantile_report
from gridsense.models.price import PriceForecaster
from gridsense.splits import assign_split


def load_train_val() -> tuple[pd.DataFrame, pd.DataFrame]:
    table = io.read("training_table").dropna(subset=["y_price"])
    split = assign_split(table["target_ts_utc"])
    return table[split == "train"], table[split == "val"]


def classify_metrics(model: LowPriceClassifier, val: pd.DataFrame) -> dict:
    pred = model.predict(val)
    metrics = {}
    for col, label in LABELS.items():
        y = val[label].astype(int)
        # k = number of positives, i.e. R-precision.
        for key, value in classification_report(y, pred[col], k=int(y.sum())).items():
            metrics[f"{col}_{key}"] = value
    return metrics


def price_metrics(model: PriceForecaster, val: pd.DataFrame) -> dict:
    pred = model.predict(val)
    cols = [c for c in pred.columns if c.startswith("price_p")]
    return quantile_report(val["y_price"], dict(zip(model.quantiles, (pred[c] for c in cols))))


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
        },
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
