import pandas as pd
import pytest

from gridsense import config
from gridsense.data.check_weather_join import join_sample, synthetic_weather, target_hours
from gridsense.data.price_features import add_price_features
from gridsense.schemas import PRICES_HOURLY, TRAINING_TABLE


def local_hour(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz=config.LOCAL_TZ).tz_convert("UTC")


def price_frame(start: str, end: str) -> pd.DataFrame:
    hours = pd.date_range(local_hour(start), local_hour(end), freq="h", inclusive="left")
    return pd.DataFrame(
        {
            "ts_utc": hours,
            "price_mean": 25,
            "price_min": 25,
            "price_max": 25,
        }
    ).astype(PRICES_HOURLY)


def test_lags_are_exact_and_independent_of_future_prices():
    prices = price_frame("2025-03-22", "2025-04-06")
    missing = local_hour("2025-03-29 13:00")
    prices = prices.loc[prices["ts_utc"].ne(missing)].copy()
    prices.loc[prices["ts_utc"].eq(local_hour("2025-03-23 13:00")), "price_mean"] = -11
    prices.loc[prices["ts_utc"].eq(local_hour("2025-03-24 06:00")), "price_mean"] = -7
    prices = prices.loc[prices["ts_utc"].ne(local_hour("2025-03-24 12:00"))]

    rows = pd.DataFrame(
        {
            "issue_ts": [local_hour("2025-03-29 10:00")] * 2,
            "target_ts_utc": [local_hour("2025-03-30 13:00"), local_hour("2025-04-05 13:00")],
        }
    )
    result = add_price_features(rows, prices)
    assert result["f_price_same_hour_d"].isna().all()
    assert result["f_price_same_hour_d_minus_6"].tolist() == [-11, -11]
    assert result["f_price_midday_mean_d"].isna().all()
    assert result["f_price_midday_min_7d"].tolist() == [-11, -11]
    assert result["f_negative_price_hours_7d"].tolist() == [2, 2]
    assert result["f_price_coverage_7d"].tolist() == pytest.approx([167 / 168] * 2)

    future_changed = prices.copy()
    future_changed.loc[future_changed["ts_utc"].ge(local_hour("2025-03-30")), "price_mean"] = -999
    pd.testing.assert_frame_equal(result, add_price_features(rows, future_changed))


def test_lag_for_ambiguous_local_hour_stays_missing():
    prices = price_frame("2025-10-19", "2025-10-28")
    rows = pd.DataFrame(
        {
            "issue_ts": [local_hour("2025-10-26 10:00")],
            "target_ts_utc": [local_hour("2025-10-27 03:00")],
        }
    )
    result = add_price_features(rows, prices)
    assert pd.isna(result["f_price_same_hour_d"].iloc[0])
    assert result["f_price_same_hour_d_minus_6"].iloc[0] == 25


def test_configured_city_sample_yields_one_price_label_per_dst_hour():
    weather = synthetic_weather()
    prices = price_frame("2025-03-22", "2025-03-31")
    result = join_sample(weather, prices)
    assert len(weather) == len(target_hours()) * len(config.WEATHER_POINTS)
    assert set(weather["location"]) == set(config.WEATHER_POINTS)
    assert len(result) == 23
    assert result["target_ts_utc"].is_unique
    assert pd.DatetimeIndex(result["target_ts_utc"]).equals(target_hours())
    assert str(result["issue_ts"].dtype) == TRAINING_TABLE["issue_ts"]
    assert result["y_price"].tolist() == [25] * 23
    assert result["f_temp_c_bucuresti"].notna().all()

    with pytest.raises(ValueError, match="weather hours"):
        join_sample(weather.iloc[1:], prices)
    with pytest.raises(ValueError, match="Missing real prices"):
        join_sample(weather, prices.loc[prices["ts_utc"].ne(target_hours()[0])])
