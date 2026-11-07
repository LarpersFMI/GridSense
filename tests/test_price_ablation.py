import pandas as pd
import pytest

from gridsense import config
from gridsense.models.ablate_price import feature_variants, validation_tables


def test_feature_variants_preserve_rows_and_leave_input_unchanged():
    table = pd.DataFrame(
        {"y_price": [10.0, 30.0], "f_hour": [12, 13], "f_load_mean_dm1": [5000, 5100],
         "f_solar_max_dm1": [None, None], "f_wind_mean_dm1": [None, None],
         "f_load_fc_min": [4000, 4100], "f_load_fc_max": [6000, 6100]}, index=[5, 8]
    )
    original = table.copy(deep=True)
    variants = feature_variants(table)
    assert variants["prices_calendar"].columns.tolist() == ["y_price", "f_hour"]
    assert "f_load_mean_dm1" in variants["lagged_load"]
    assert "f_load_fc_min" not in variants["lagged_load"]
    for variant in variants.values():
        pd.testing.assert_series_equal(variant["y_price"], table["y_price"])
    pd.testing.assert_frame_equal(table, original)


def test_feature_variants_require_week_ahead_features():
    with pytest.raises(ValueError, match="Rebuild features"):
        feature_variants(pd.DataFrame({"y_price": [1.0]}))


def test_weather_has_its_own_variant_not_a_mislabelled_calendar_baseline():
    table = pd.DataFrame({"y_price": [1.0], "f_load_fc_min": [5000],
                          "f_load_fc_max": [7000], "f_temp_mean": [20], "f_ghi_mean": [500]})
    variants = feature_variants(table)
    assert "f_temp_mean" not in variants["prices_calendar"]
    assert "f_ghi_mean" not in variants["lagged_load_week_ahead"]
    pd.testing.assert_frame_equal(variants["lagged_load_week_ahead_weather"], table)


def test_validation_tables_exclude_test_unassigned_and_unlabelled_rows():
    timestamps = pd.DatetimeIndex(
        [config.TRAIN_START, config.VAL_START, config.TEST_START,
         config.VAL_END + pd.Timedelta(days=2), config.VAL_START + pd.Timedelta(days=1)]
    ).tz_convert("UTC")
    table = pd.DataFrame({"target_ts_utc": timestamps, "y_price": [1.0, 2.0, 3.0, 4.0, None]})
    train, val = validation_tables(table)
    assert train.index.tolist() == [0]
    assert val.index.tolist() == [1]


def test_validation_tables_require_both_splits():
    table = pd.DataFrame({"target_ts_utc": [config.TEST_START], "y_price": [1.0]})
    with pytest.raises(ValueError, match="train split and validation"):
        validation_tables(table)