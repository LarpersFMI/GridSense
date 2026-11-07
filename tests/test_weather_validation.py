import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.models.weather_validation import (
    classification_scores,
    cross_calibrated_predictions,
    has_weather,
)


def test_weather_feature_detection_does_not_confuse_actual_grid_lags():
    assert not has_weather(["f_wind_mean_dm1", "f_load_mean_dm1"])
    assert has_weather(["f_ghi_mean"])
    assert has_weather(["f_wind100_constanta"])


def test_classification_scores_use_only_the_supplied_rows():
    rows = pd.DataFrame({"horizon_days": [1, 1, 2, 2],
                         "y_near_zero": [1, 0, 1, 0], "y_cheap": [1, 0, 0, 0]}, index=[5, 6, 7, 8])
    pred = pd.DataFrame({"p_near_zero": [0.9, 0.1, 0.8, 0.2],
                         "p_cheap": [0.8, 0.1, 0.2, 0.1]}, index=rows.index)
    report = classification_scores(rows, pred)
    assert report[report.horizon.eq("all")]["n"].tolist() == [4, 4]
    assert report[report.horizon.eq("all")]["positives"].tolist() == [2, 1]


def test_classification_scores_reject_missing_probabilities():
    rows = pd.DataFrame({"horizon_days": [1], "y_near_zero": [1], "y_cheap": [1]})
    pred = pd.DataFrame({"p_near_zero": [np.nan], "p_cheap": [0.8]})
    with pytest.raises(ValueError, match="finite"):
        classification_scores(rows, pred)


def test_month_cross_fit_excludes_every_horizon_of_held_target_labels():
    target = pd.date_range("2025-03-01", "2025-05-31", freq="6h", tz="UTC")
    local = target.tz_convert(config.LOCAL_TZ)
    rows = pd.DataFrame({"target_ts_utc": target, "y_near_zero": local.hour >= 12,
                         "y_cheap": local.hour >= 18})
    rows = pd.concat([rows.assign(horizon_days=h) for h in (1, 2)], ignore_index=True)
    raw = pd.DataFrame({"p_near_zero": np.linspace(0.1, 0.8, len(rows)),
                        "p_cheap": np.linspace(0.1, 0.4, len(rows))})
    held = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.month.eq(3)
    flipped = rows.copy()
    flipped.loc[held, ["y_near_zero", "y_cheap"]] = ~flipped.loc[held, ["y_near_zero", "y_cheap"]]
    before = cross_calibrated_predictions(rows, raw)
    after = cross_calibrated_predictions(flipped, raw)
    pd.testing.assert_frame_equal(before.loc[held], after.loc[held])
    assert before["p_near_zero"].between(0, 1).all()


def test_month_cross_fit_requires_distinct_months_and_aligned_predictions():
    rows = pd.DataFrame({"target_ts_utc": pd.to_datetime(["2025-03-01T00:00Z"]),
                         "y_near_zero": [1], "y_cheap": [0]})
    raw = pd.DataFrame({"p_near_zero": [0.5], "p_cheap": [0.2]})
    with pytest.raises(ValueError, match="two target months"):
        cross_calibrated_predictions(rows, raw)
    rows = pd.concat([rows, rows.assign(target_ts_utc=pd.Timestamp("2025-04-01", tz="UTC"))],
                     ignore_index=True)
    raw = pd.concat([raw, raw], ignore_index=True).set_axis([5, 6])
    with pytest.raises(ValueError, match="align"):
        cross_calibrated_predictions(rows, raw)