import numpy as np
import pytest
from sklearn.metrics import average_precision_score, brier_score_loss

from gridsense.models import train
from gridsense.models.calibrate import (
    CALIBRATORS,
    cross_fit,
    fit_calibrator,
    plot_reliability,
    reliability_table,
)
from gridsense.models.classify import LowPriceClassifier
from gridsense.splits import assign_split


def _too_low(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """True event probability q; a 'model' that reports q / 3, i.e. three times too pessimistic."""
    rng = np.random.default_rng(seed)
    q = rng.uniform(0, 0.6, n)
    y = (rng.uniform(0, 1, n) < q).astype(int)
    return q / 3, y, q


@pytest.mark.parametrize("method", list(CALIBRATORS))
def test_calibration_fixes_pessimistic_probabilities(method):
    p_fit, y_fit, _ = _too_low(5000, seed=0)
    p_new, y_new, q_new = _too_low(5000, seed=1)
    calibrated = fit_calibrator(p_fit, y_fit, method).predict(p_new)

    assert brier_score_loss(y_new, calibrated) < brier_score_loss(y_new, p_new)
    # On average, the calibrated probability is back near the true one (raw was 3x too low).
    assert abs(calibrated.mean() - q_new.mean()) < 0.02
    assert abs(p_new.mean() - q_new.mean()) > 0.15
    assert calibrated.min() >= 0 and calibrated.max() <= 1


@pytest.mark.parametrize("method", list(CALIBRATORS))
def test_calibration_keeps_the_order_of_hours(method):
    p, y, _ = _too_low(2000)
    order = np.argsort(p)
    assert np.all(np.diff(fit_calibrator(p, y, method).predict(p[order])) >= 0)


def test_platt_keeps_ranking_exactly_isotonic_creates_ties():
    p, y, _ = _too_low(2000)
    platt = fit_calibrator(p, y, "platt").predict(p)
    iso = fit_calibrator(p, y, "isotonic").predict(p)

    assert average_precision_score(y, platt) == pytest.approx(average_precision_score(y, p))
    assert len(np.unique(platt)) == len(np.unique(p))
    assert len(np.unique(iso)) < len(np.unique(p)) / 10


def test_cross_fit_never_uses_a_groups_own_labels():
    p, y, _ = _too_low(3000)
    groups = np.repeat([1, 2, 3], 1000)
    flipped = y.copy()
    flipped[groups == 1] = 1 - flipped[groups == 1]

    a, b = cross_fit(p, y, groups), cross_fit(p, flipped, groups)
    assert np.array_equal(a[groups == 1], b[groups == 1])
    assert not np.array_equal(a[groups == 2], b[groups == 2])


def test_reliability_table_and_plot(tmp_path):
    p, y, q = _too_low(5000)
    honest = reliability_table(q, y)
    assert honest["rows"].sum() == len(y)
    assert np.allclose(honest["predicted"], honest["observed"], atol=0.05)
    # The pessimistic model's bins sit above the diagonal: observed > predicted.
    pessimistic = reliability_table(p, y)
    assert (pessimistic["observed"] > pessimistic["predicted"]).all()

    path = tmp_path / "reliability.png"
    plot_reliability({"raw": pessimistic, "true q": honest}, path, title="test")
    assert path.stat().st_size > 0


@pytest.mark.parametrize("method", list(CALIBRATORS))
def test_classifier_calibrates_on_val(tiny_training_table, method):
    split = assign_split(tiny_training_table["target_ts_utc"])
    tr, val = tiny_training_table[split == "train"], tiny_training_table[split == "val"]
    model = LowPriceClassifier(calibration=method).fit(tr, val)

    assert set(model.calibrators) == {"p_near_zero", "p_cheap_given_near_zero"}
    meta = model.metadata()
    assert meta["calibration"] == method
    assert meta["calibrated"] == ["p_cheap_given_near_zero", "p_near_zero"]
    raw = model.predict(val, apply_calibration=False)
    cal = model.predict(val)
    assert not np.allclose(raw["p_near_zero"], cal["p_near_zero"])
    assert cal["p_near_zero"].between(0, 1).all()

    metrics = train.classify_metrics(model, val)
    assert {"p_near_zero_brier", "p_near_zero_cal_brier", "p_cheap_cal_pr_auc"} <= set(metrics)


def test_classifier_without_val_or_calibration_stays_raw(tiny_training_table):
    split = assign_split(tiny_training_table["target_ts_utc"])
    tr, val = tiny_training_table[split == "train"], tiny_training_table[split == "val"]
    assert LowPriceClassifier().fit(tr).calibrators == {}
    model = LowPriceClassifier(calibration=None).fit(tr, val)
    assert model.calibrators == {}
    assert "p_near_zero_cal_brier" not in train.classify_metrics(model, val)
