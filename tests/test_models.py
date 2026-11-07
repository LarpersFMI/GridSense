import numpy as np
import pandas as pd
import pytest

from gridsense import config, io
from gridsense.models import predict, train
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.price import PriceForecaster
from gridsense.splits import assign_split
from gridsense.synthetic import predictions as fake_predictions


def _split(table):
    split = assign_split(table["target_ts_utc"])
    return table[split == "train"], table[split == "val"]


def test_classifier_outputs_probabilities(tiny_training_table):
    tr, val = _split(tiny_training_table)
    out = LowPriceClassifier().fit(tr, val).predict(val)
    for col in ("p_near_zero", "p_cheap"):
        assert out[col].between(0, 1).all()
    assert out["price_p50"].isna().all()


def test_price_quantiles_never_cross(tiny_training_table):
    tr, val = _split(tiny_training_table)
    out = PriceForecaster().fit(tr, val).predict(val)
    assert (out["price_p10"] <= out["price_p50"]).all()
    assert (out["price_p50"] <= out["price_p90"]).all()
    assert out["p_near_zero"].isna().all()


def test_train_then_predict_end_to_end(tiny_training_table, tmp_dirs):
    io.write(tiny_training_table, "training_table")
    train.main([])
    predict.main([])

    preds = io.read("predictions")
    assert len(preds) > 0
    assert preds["model_name"].iloc[0] == "lgbm_classifier+lgbm_quantile"
    assert (config.REPORTS_DIR / "experiments.csv").exists()


def test_fake_predictions_are_consistent():
    start = pd.Timestamp("2026-03-27", tz=config.LOCAL_TZ)
    end = pd.Timestamp("2026-03-31", tz=config.LOCAL_TZ)
    preds = fake_predictions.generate(start, end)

    io.check_columns(preds, "predictions")
    assert set(preds["horizon_days"]) == set(config.HORIZONS_DAYS)
    assert (preds["p_cheap"] <= preds["p_near_zero"]).all()
    assert (preds["price_p10"] <= preds["price_p90"]).all()
    # 2026-03-29 is the spring DST switch: 23 local hours.
    issue = preds["issue_ts"].min()
    day = preds[(preds["issue_ts"] == issue) & (preds["horizon_days"] == 2)]
    assert len(day) == 23
    assert np.isfinite(preds[["p_near_zero", "price_p50"]].to_numpy()).all()


def test_fake_predictions_refuse_real_mode(monkeypatch):
    monkeypatch.setattr(config, "DATA_MODE", "real")
    with pytest.raises(SystemExit):
        fake_predictions.main([])
