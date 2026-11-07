import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from gridsense import config, io
from gridsense.data.build_regional import add_regional_features
from gridsense.features.build import main as build_main
from gridsense.features.regional import (
    REGIONAL_COLUMNS,
    join_regional_features,
    read_regional_table,
)
from gridsense.schemas import CALENDAR, GRID_HOURLY, PRICES_HOURLY


def rows(issue_day="2025-03-29", horizon=1):
    day = pd.Timestamp(issue_day)
    target_day = (day + pd.Timedelta(days=horizon)).tz_localize(config.LOCAL_TZ)
    end = (day + pd.Timedelta(days=horizon + 1)).tz_localize(config.LOCAL_TZ)
    target = pd.date_range(target_day, end, freq="h", inclusive="left").tz_convert("UTC")
    issue = (day + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    return pd.DataFrame({"issue_ts": issue, "target_ts_utc": target, "horizon_days": horizon,
                         "y_price": np.arange(len(target), dtype=float), "f_hour": target.hour},
                        index=np.arange(len(target)) * 2 + 100)


def regional(training):
    return training[["issue_ts", "target_ts_utc", "horizon_days"]].assign(
        **{c: 5000.0 if "load" in c else 10.0 for c in REGIONAL_COLUMNS}
    )


def test_join_preserves_original_rows_indexes_and_labels_with_sparse_inputs():
    training = rows().iloc[::-1].copy()
    r = regional(training).iloc[1:].copy()
    r["y_price"] = -9999.0  # Labels in a source table must never overwrite training labels.
    joined, missing = join_regional_features(training, r)
    pd.testing.assert_frame_equal(joined[training.columns], training)
    assert missing == 1
    assert joined.iloc[0][list(REGIONAL_COLUMNS)].isna().all()
    assert joined.iloc[0].data_quality == "missing_regional"
    assert joined.iloc[1:].data_quality.eq("ok").all()


def test_duplicate_keys_and_existing_feature_overlap_fail():
    t = rows()
    r = regional(t)
    with pytest.raises(ValueError, match="unique"):
        join_regional_features(t, pd.concat([r, r.iloc[[0]]]))
    with pytest.raises(ValueError, match="already exist"):
        join_regional_features(t.assign(**{REGIONAL_COLUMNS[0]: 1.0}), r)


def test_invalid_clock_horizon_and_features_fail():
    t = rows()
    r = regional(t)
    with pytest.raises(ValueError, match="clock/horizon"):
        join_regional_features(t, r.assign(issue_ts=r.issue_ts + pd.Timedelta(hours=1)))
    with pytest.raises(ValueError, match="11 documented"):
        join_regional_features(t, r.assign(f_future_actual_price=100.0))
    with pytest.raises(ValueError, match="infinite"):
        join_regional_features(t, r.assign(**{REGIONAL_COLUMNS[0]: np.inf}))


@pytest.mark.parametrize("issue_day,expected_hours", [("2025-03-29", 23), ("2025-10-25", 25)])
def test_dst_forecasts_remain_unique_and_fully_joined(issue_day, expected_hours):
    t = rows(issue_day)
    joined, missing = join_regional_features(t, regional(t))
    assert len(joined) == expected_hours and missing == 0
    assert joined.target_ts_utc.nunique() == expected_hours


def test_missing_region_reason_does_not_erase_weather_quality():
    t = rows().assign(data_quality="missing_weather")
    joined, _ = join_regional_features(t, regional(t).iloc[:0])
    assert joined.data_quality.eq("missing_weather;missing_regional").all()


def test_only_issue_day_prices_and_previous_day_load_affect_regional_features():
    t = rows("2025-03-20", horizon=7)
    issue_day = t.issue_ts.iloc[0].tz_convert(config.LOCAL_TZ).normalize()
    hours = pd.date_range(issue_day - pd.DateOffset(days=8), issue_day + pd.DateOffset(days=9),
                          freq="h", inclusive="left").tz_convert("UTC")
    prices = pd.concat([pd.DataFrame({"ts_utc": hours, "price_mean": value,
                                     "price_min": value, "price_max": value,
                                     "country_code": country})
                        for country, value in (("RO", 80.0), ("HU", 60.0), ("BG", 70.0))],
                       ignore_index=True)
    load = pd.concat([pd.DataFrame({"ts_utc": hours, "load_actual_mw": value,
                                   "country_code": country})
                      for country, value in (("RO", 6000.0), ("HU", 5000.0), ("BG", 4000.0))],
                     ignore_index=True)
    base = add_regional_features(t, prices, load)
    future_prices = prices.copy()
    price_day = prices.ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.normalize()
    future_prices.loc[price_day.gt(issue_day), ["price_mean", "price_min", "price_max"]] += 500
    future_load = load.copy()
    load_day = load.ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.normalize()
    future_load.loc[load_day.ge(issue_day), "load_actual_mw"] *= 2
    changed = add_regional_features(t, future_prices, future_load)
    pd.testing.assert_frame_equal(base[list(REGIONAL_COLUMNS)], changed[list(REGIONAL_COLUMNS)])
    # Sensitivity: the check cannot pass just because the producer ignores neighbour inputs.
    known_prices = prices.copy()
    known_prices.loc[price_day.eq(issue_day) & prices.country_code.eq("HU"),
                     ["price_mean", "price_min", "price_max"]] += 10
    known = add_regional_features(t, known_prices, load)
    assert known.f_price_hu_same_hour_d.sub(base.f_price_hu_same_hour_d).eq(10).all()
    assert known.f_price_spread_ro_hu_d.sub(base.f_price_spread_ro_hu_d).eq(-10).all()
    assert known.f_load_hu_same_hour_d_minus_1.equals(base.f_load_hu_same_hour_d_minus_1)


def test_read_verifies_manifest_before_using_collected_features(tmp_dirs):
    t = rows()
    r = regional(t)
    config.PROCESSED_DIR.mkdir()
    path = config.PROCESSED_DIR / "regional_market_features.parquet"
    r.to_parquet(path, index=False)
    manifest = {"outputs": {path.name: {"rows": len(r), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}}
    m = config.PROCESSED_DIR / "regional_market_manifest.json"
    m.write_text(json.dumps(manifest))
    data, info = read_regional_table()
    assert len(data) == len(t) and info["sha256"] == manifest["outputs"][path.name]["sha256"]
    manifest["outputs"][path.name]["sha256"] = "incorrect"
    m.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="checksum"):
        read_regional_table()


def test_feature_cli_is_opt_in_and_preserves_default_rows(tmp_dirs, monkeypatch):
    monkeypatch.setattr(config, "DATA_MODE", "real")
    first = config.VAL_START
    times = pd.date_range(first, first + pd.DateOffset(days=10), freq="h", inclusive="left")
    calendar = pd.DataFrame({"ts_utc": times.tz_convert("UTC"), "is_holiday": False,
                             "is_bridge_day": False, "is_dst": False, "day_hours": 24}).astype(CALENDAR)
    prices = pd.DataFrame({"ts_utc": times.tz_convert("UTC"), "price_mean": 50.0,
                           "price_min": 50.0, "price_max": 50.0}).astype(PRICES_HOURLY)
    grid = pd.DataFrame({"ts_utc": times.tz_convert("UTC"), "load_actual_mw": 5000.0,
                         "solar_actual_mw": np.nan, "wind_actual_mw": np.nan}).astype(GRID_HOURLY)
    for name, table in (("calendar", calendar), ("prices_hourly", prices), ("grid_hourly", grid)):
        io.write(table, name)
    build_main([])
    baseline = io.read("training_table")
    reg = regional(baseline)
    path = config.PROCESSED_DIR / "regional_market_features.parquet"
    reg.to_parquet(path, index=False)
    (config.PROCESSED_DIR / "regional_market_manifest.json").write_text(json.dumps({
        "outputs": {path.name: {"rows": len(reg), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
    }))
    build_main(["--regional"])
    joined = io.read("training_table")
    assert set(REGIONAL_COLUMNS).issubset(joined.columns)
    pd.testing.assert_frame_equal(joined[baseline.columns], baseline)
    build_main([])
    pd.testing.assert_frame_equal(io.read("training_table"), baseline)


def test_real_regional_inputs_cannot_enter_fake_feature_build(monkeypatch):
    monkeypatch.setattr(config, "DATA_MODE", "fake")
    with pytest.raises(SystemExit):
        build_main(["--regional"])