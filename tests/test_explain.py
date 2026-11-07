import re

import numpy as np
import pandas as pd
import pytest

from gridsense import io
from gridsense.models import predict, train
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.explain import (
    describe_top_features,
    feature_phrase,
    shap_values,
    top_features,
)
from gridsense.splits import assign_split


@pytest.fixture
def fitted(tiny_training_table):
    split = assign_split(tiny_training_table["target_ts_utc"])
    tr, val = tiny_training_table[split == "train"], tiny_training_table[split == "val"]
    clf = LowPriceClassifier().fit(tr, val)
    return clf.models["p_near_zero"], val[clf.features]


def test_shap_values_add_up_to_the_model_score(fitted):
    model, X = fitted
    contrib = model.booster_.predict(X, pred_contrib=True)
    base = contrib[:, -1]
    raw_score = model.booster_.predict(X, raw_score=True)
    assert np.allclose(base + shap_values(model, X).sum(axis=1), raw_score)


def test_top_features_format_and_order(fitted):
    model, X = fitted
    text = top_features(model, X, n=3)

    assert text.index.equals(X.index)
    # Only 2 features exist, so n is capped; the f_ prefix is dropped.
    pattern = re.compile(r"^(solar|weekend):[+-]\d+\.\d\d; (solar|weekend):[+-]\d+\.\d\d$")
    assert text.map(lambda s: bool(pattern.match(s))).all()

    values = text.str.findall(r"[+-]\d+\.\d\d").map(lambda v: [abs(float(x)) for x in v])
    assert values.map(lambda v: v == sorted(v, reverse=True)).all()


def test_top_features_point_the_right_way(fitted):
    """Price falls with solar in the fixture, so strong sun must push toward 'cheap'."""
    model, X = fitted
    sunny = X["f_solar"] > 0.95
    assert sunny.any()
    text = top_features(model, X[sunny], n=1)
    assert text.str.startswith("solar:+").all()


def test_chain_explanation_sums_both_step_models(tiny_training_table):
    split = assign_split(tiny_training_table["target_ts_utc"])
    tr, val = tiny_training_table[split == "train"], tiny_training_table[split == "val"]
    clf = LowPriceClassifier().fit(tr, val)
    X = val[clf.features]

    models = clf.explain_models("p_cheap")
    assert len(models) == 2 and clf.explain_models("p_near_zero") == models[:1]
    both = shap_values(models, X)
    assert np.allclose(both, shap_values(models[0], X) + shap_values(models[1], X))
    assert top_features(models, X).str.contains(":").all()


def test_predictions_carry_top_features(tiny_training_table, tmp_dirs):
    io.write(tiny_training_table, "training_table")
    train.main([])
    path = predict.main([])

    preds = pd.read_parquet(path)
    assert preds["top_features"].str.contains(":").all()


def test_feature_phrases_are_readable():
    assert feature_phrase("f_ghi_mean") == "sunshine forecast"
    assert feature_phrase("ghi_constanta") == "sunshine forecast in Constanța"
    assert feature_phrase("doy_cos_1") == "time of year"
    assert feature_phrase("price_same_hour_target_m7") == "price at this hour a week earlier"
    assert feature_phrase("neg_hours_7d") == "recent negative-price hours"
    assert feature_phrase("some_new_feature") == "some new feature"  # unknown: still readable


def test_top_features_text_splits_for_and_against_and_merges_duplicates():
    top = pd.Series(
        [
            "doy_cos_1:+1.15; wind100_constanta:+0.83; hour:-0.30",
            "doy_sin_1:+0.40; doy_cos_2:+0.20",
            "",
        ]
    )
    text = describe_top_features(top).tolist()
    assert text[0] == (
        "Pointing to a low price: time of year, wind forecast in Constanța. Against: hour of day."
    )
    assert text[1] == "Pointing to a low price: time of year."
    assert text[2] == ""


def test_predictions_carry_readable_explanations(tiny_training_table, tmp_dirs):
    io.write(tiny_training_table, "training_table")
    train.main([])
    preds = pd.read_parquet(predict.main([]))
    assert preds["top_features_text"].str.contains("low price|Against").all()
