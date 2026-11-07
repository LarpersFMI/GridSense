import argparse

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.base import PRICE_COLUMNS, PROBA_COLUMNS
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.explain import top_features
from gridsense.models.price import PriceForecaster

KEY_COLUMNS = ["issue_ts", "target_ts_utc", "horizon_days"]
EXPLAINED = "p_cheap"


def build_predictions(
    table: pd.DataFrame,
    classifier: LowPriceClassifier,
    price: PriceForecaster,
    model_version: str,
) -> pd.DataFrame:
    out = table[KEY_COLUMNS].copy()
    out[list(PROBA_COLUMNS)] = classifier.predict(table)[list(PROBA_COLUMNS)]
    out[list(PRICE_COLUMNS)] = price.predict(table)[list(PRICE_COLUMNS)]
    # Until data/quality.py feeds per-row flags into the training table.
    out["data_quality"] = table.get("data_quality", "ok")
    # Explains p_cheap: the probability the agent's decision rule acts on.
    model = classifier.models[EXPLAINED]
    out["top_features"] = top_features(model, table[classifier.features]).to_numpy()
    out["model_name"] = f"{classifier.name}+{price.name}"
    out["model_version"] = model_version
    return out.reset_index(drop=True)


def issue_dates_local(table: pd.DataFrame) -> pd.Series:
    return table["issue_ts"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Score issue dates and write the predictions table."
    )
    parser.add_argument(
        "--start", help="First issue date (YYYY-MM-DD). Default: latest issue date."
    )
    parser.add_argument("--end", help="Last issue date (YYYY-MM-DD). Default: same as --start.")
    args = parser.parse_args(argv)

    table = io.read("training_table")
    dates = issue_dates_local(table)
    if args.start:
        mask = dates.between(pd.Timestamp(args.start), pd.Timestamp(args.end or args.start))
    else:
        mask = dates == dates.max()
    if not mask.any():
        raise SystemExit("no rows in training_table for the requested issue dates")

    classifier, clf_version = artifacts.load_latest(LowPriceClassifier.name)
    price, price_version = artifacts.load_latest(PriceForecaster.name)
    preds = build_predictions(table[mask], classifier, price, f"{clf_version}+{price_version}")
    io.write(preds, "predictions")
    print(f"[{config.DATA_MODE}] wrote {len(preds)} predictions to {config.PROCESSED_DIR}")


if __name__ == "__main__":
    main()
