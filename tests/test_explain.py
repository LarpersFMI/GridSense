import re

import numpy as np
import pytest

from gridsense import io
from gridsense.models import predict, train
from gridsense.models.classify import LowPriceClassifier
from gridsense.models.explain import shap_values, top_features
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
    predict.main([])

    preds = io.read("predictions")
    assert preds["top_features"].str.contains(":").all()
