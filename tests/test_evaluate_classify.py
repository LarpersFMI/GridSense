import numpy as np
import pandas as pd
import pytest

from gridsense import config, io
from gridsense.models import artifacts, evaluate, train
from gridsense.models.classify import LowPriceClassifier
from gridsense.splits import assign_split


@pytest.fixture
def table_with_weather(tiny_training_table):
    """tiny_training_table plus the columns the solar rule reads."""
    t = tiny_training_table
    return t.assign(f_ghi_mean=t["f_solar"] * 900, f_is_weekend=t["f_weekend"], f_is_holiday=0)


def test_evaluate_classify_compares_models_by_horizon(table_with_weather, tmp_dirs):
    io.write(table_with_weather, "training_table")
    train.main(["--task", "classify"])
    evaluate.main(["--task", "classify"])

    out_dir = config.REPORTS_DIR / "eval"
    result = pd.read_csv(out_dir / "classify_val.csv")
    models = {"climatology", "solar_rule", "lgbm_classifier", "lgbm_classifier_raw"}
    assert set(result["model"]) == models
    assert set(result["label"]) == {"p_near_zero", "p_cheap"}
    assert set(result["horizon"].astype(str)) == {"all", "1"}
    assert len(result) == len(models) * 2 * 2

    clim = result[result["model"] == "climatology"]
    assert np.allclose(clim["pr_auc_vs_clim"], 1.0)
    assert result["pr_auc"].between(0, 1).all()
    for col in ("p_near_zero", "p_cheap"):
        assert (out_dir / f"reliability_{col}_val.png").stat().st_size > 0


def test_val_scores_use_cross_fitted_calibration(table_with_weather, tmp_dirs):
    split = assign_split(table_with_weather["target_ts_utc"])
    tr, val = table_with_weather[split == "train"], table_with_weather[split == "val"]
    clf = LowPriceClassifier().fit(tr, val)
    artifacts.save(clf, {"task": "classify"})

    on_val = evaluate.classify_models(tr, val, on_val=True)["lgbm_classifier"](val)
    on_test = evaluate.classify_models(tr, val, on_val=False)["lgbm_classifier"](val)
    # On val the saved (in-sample) calibrators are not used; elsewhere they are.
    assert not np.allclose(on_val["p_near_zero"], clf.predict(val)["p_near_zero"])
    assert np.allclose(on_test["p_near_zero"], clf.predict(val)["p_near_zero"])


def test_solar_rule_is_skipped_without_weather(tiny_training_table, tmp_dirs, capsys):
    split = assign_split(tiny_training_table["target_ts_utc"])
    tr, val = tiny_training_table[split == "train"], tiny_training_table[split == "val"]
    models = evaluate.classify_models(tr, val, on_val=True)
    assert "climatology" in models and "solar_rule" not in models
    assert "skipping solar_rule" in capsys.readouterr().out
