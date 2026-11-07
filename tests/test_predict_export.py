"""predictions.parquet must only carry data_quality values the app's schema accepts."""

import pandas as pd

from gridsense import config, io
from gridsense.models import predict, train
from gridsense.models.predict import APP_DATA_QUALITY, export_data_quality


def test_flags_outside_the_app_enum_become_degraded_with_their_reason():
    detail = pd.Series(["ok", "missing_weather", "degraded", "failed", None, "regional_missing"])
    status, reason = export_data_quality(detail)

    assert status.tolist() == ["ok", "degraded", "degraded", "failed", "degraded", "degraded"]
    assert reason.tolist() == [
        "",
        "missing_weather",
        "degraded",
        "failed",
        "unknown",
        "regional_missing",
    ]
    assert status.isin(APP_DATA_QUALITY).all()


def test_predictions_file_is_app_compatible(tiny_training_table, tmp_dirs):
    rng_rows = tiny_training_table.index % 3 == 0
    table = tiny_training_table.assign(data_quality="ok")
    table.loc[rng_rows, "data_quality"] = "missing_weather"
    io.write(table, "training_table")
    train.main([])
    path = predict.main(["--start", "2025-08-01", "--end", "2025-08-29"])

    preds = pd.read_parquet(path)
    assert preds["data_quality"].isin(APP_DATA_QUALITY).all()
    degraded = preds["data_quality"] == "degraded"
    assert (
        degraded.any() and (preds.loc[degraded, "data_quality_reason"] == "missing_weather").all()
    )
    assert (preds.loc[~degraded, "data_quality_reason"] == "").all()


def test_tables_without_flags_export_ok(tiny_training_table, tmp_dirs):
    io.write(tiny_training_table, "training_table")
    train.main([])
    preds = pd.read_parquet(predict.main([]))
    assert (preds["data_quality"] == "ok").all() and (preds["data_quality_reason"] == "").all()


def test_make_predict_never_writes_the_apps_dataset(tiny_training_table, tmp_dirs):
    """DATASET_DIR/predictions.parquet is the app's append-only history; only its pipeline writes it."""
    io.write(tiny_training_table, "training_table")
    train.main([])
    path = predict.main([])

    assert not (config.PROCESSED_DIR / "predictions.parquet").exists()
    assert path.parent == config.REPORTS_DIR / "predictions"
    io.check_columns(pd.read_parquet(path), "predictions")
