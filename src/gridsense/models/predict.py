"""Predictions for the app. Owner: ML-C.

build_predictions() is the contract: the app's `forecast` pipeline (src/gridsense/pipelines) calls it on
the day's issue rows and appends the result to DATASET_DIR/predictions.parquet, the append-only run
history the Watchdog reads. This module's CLI (`make predict`) never writes there: it writes a local
copy to reports/<mode>/predictions/ for inspection.
"""

import argparse
from pathlib import Path

import pandas as pd

from gridsense import config, io
from gridsense.models import artifacts
from gridsense.models.base import PRICE_COLUMNS, PROBA_COLUMNS
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.explain import describe_top_features, top_features
from gridsense.models.price import PriceForecaster

KEY_COLUMNS = ["issue_ts", "target_ts_utc", "horizon_days"]
EXPLAINED = "p_cheap"

# The app accepts only these (packages/shared/domain/Dataset/Predictions.ts, Predictions.DataQuality):
# one other value makes the Watchdog's whole check fail. `degraded`: an input was missing and a fallback
# was used; `failed`: input checks failed.
APP_DATA_QUALITY = ("ok", "degraded", "failed")


def export_data_quality(detail: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(data_quality, data_quality_reason) for the app, from the training table's detailed flags.

    Any flag outside APP_DATA_QUALITY (e.g. "missing_weather") becomes "degraded"; a missing flag also
    becomes "degraded" (we can't vouch for the inputs). The detailed flag is kept as the reason, so
    nothing is lost: "" when ok, otherwise the original value ("unknown" if it was missing).
    """
    detail = detail.astype("string")
    status = detail.where(detail.isin(APP_DATA_QUALITY), "degraded").fillna("degraded")
    reason = detail.fillna("unknown").where(status != "ok", "")
    return status.astype("string"), reason.astype("string")


def build_predictions(
    table: pd.DataFrame,
    classifier: LowPriceClassifier,
    price: PriceForecaster,
    model_version: str,
) -> pd.DataFrame:
    """One row per (issue_ts, target_ts_utc) of `table`, with every schemas.PREDICTIONS column plus the
    loose extras data_quality_reason and top_features_text."""
    out = table[KEY_COLUMNS].copy()
    out[list(PROBA_COLUMNS)] = classifier.predict(table)[list(PROBA_COLUMNS)]
    out[list(PRICE_COLUMNS)] = price.predict(table)[list(PRICE_COLUMNS)]
    # Per-row input flags from the training table (features/build.py); "ok" for tables without them.
    detail = table.get("data_quality", pd.Series("ok", index=table.index))
    out["data_quality"], out["data_quality_reason"] = export_data_quality(detail)
    # Explains p_cheap (both chain steps), the probability that sets a slot's cost and priority.
    models = classifier.explain_models(EXPLAINED)
    out["top_features"] = top_features(models, table[classifier.features]).to_numpy()
    out["top_features_text"] = describe_top_features(out["top_features"]).to_numpy()
    out["model_name"] = f"{classifier.name}+{price.name}"
    out["model_version"] = model_version
    return out.reset_index(drop=True)


def issue_dates_local(table: pd.DataFrame) -> pd.Series:
    return table["issue_ts"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()


def output_path(first: pd.Timestamp, last: pd.Timestamp) -> Path:
    """reports/<mode>/predictions/predictions_<first>[_<last>].parquet: never the app's DATASET_DIR."""
    name = f"predictions_{first:%Y-%m-%d}" + ("" if first == last else f"_{last:%Y-%m-%d}")
    return config.REPORTS_DIR / "predictions" / f"{name}.parquet"


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(
        description="Score issue dates into a local predictions file (not the app's dataset)."
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
    io.check_columns(preds, "predictions")

    path = output_path(dates[mask].min(), dates[mask].max())
    path.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(path, index=False)
    print(f"[{config.DATA_MODE}] wrote {len(preds)} predictions to {path}")
    return path


if __name__ == "__main__":
    main()
