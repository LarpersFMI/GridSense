"""The classifier's probabilities must be nested: P(price <= 0) <= P(price <= 20), always."""

import numpy as np
import pytest

from gridsense import config
from gridsense.models.calibrate import CALIBRATORS, cross_fit
from gridsense.models.classify import LowPriceClassifier
from gridsense.splits import assign_split


def _split(table):
    split = assign_split(table["target_ts_utc"])
    return table[split == "train"], table[split == "val"]


def _month(table):
    return table["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ).dt.month.to_numpy()


@pytest.mark.parametrize("method", [*CALIBRATORS, None])
def test_p_cheap_never_exceeds_p_near_zero(tiny_training_table, method):
    tr, val = _split(tiny_training_table)
    clf = LowPriceClassifier(calibration=method).fit(tr, val)

    outputs = {
        "raw": clf.predict(val, apply_calibration=False),
        "calibrated": clf.predict(val),
        "cross-fitted": clf.predict_cross_fitted(val, _month(val)),
    }
    for name, out in outputs.items():
        assert (out["p_cheap"] <= out["p_near_zero"]).all(), name
        assert out[["p_cheap", "p_near_zero"]].stack().between(0, 1).all(), name


def test_conditional_step_ignores_rows_above_20(tiny_training_table):
    """Labels of hours above 20 €/MWh must not affect P(cheap | near zero) at all."""
    tr, val = _split(tiny_training_table)
    tampered = tr.copy()
    above = ~tampered["y_near_zero"]
    # Impossible on purpose (cheap but not near zero): only the chain's row filter hides it.
    tampered.loc[above, "y_cheap"] = True

    a = LowPriceClassifier().fit(tr, val).predict(val)
    b = LowPriceClassifier().fit(tampered, val).predict(val)
    assert np.allclose(a, b, equal_nan=True)


def test_cross_fit_mask_limits_fitting_rows_only():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 3000)
    y = (rng.uniform(0, 1, 3000) < p).astype(int)
    groups = np.repeat([1, 2, 3], 1000)
    mask = rng.uniform(0, 1, 3000) < 0.5

    flipped = y.copy()
    flipped[~mask] = 1 - flipped[~mask]
    a = cross_fit(p, y, groups, fit_mask=mask)
    b = cross_fit(p, flipped, groups, fit_mask=mask)
    assert np.array_equal(a, b)  # masked-out labels are never fitted on
    assert np.isfinite(a).all()  # but every row still gets a probability


def test_old_unnested_artifact_asks_for_retraining(tiny_training_table):
    tr, val = _split(tiny_training_table)
    clf = LowPriceClassifier().fit(tr, val)
    clf.models = {"p_near_zero": clf.models["p_near_zero"], "p_cheap": clf.models["p_near_zero"]}
    with pytest.raises(ValueError, match="retrain"):
        clf.predict(val)
