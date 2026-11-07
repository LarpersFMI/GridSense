import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.data.weather import (
    EXTRA_VARIABLES,
    MAX_OFFSET,
    PUBLICATION_BUFFER_HOURS,
    VARIABLES,
    _month_ranges,
    merge_extra,
    parse_forecasts,
    select_offsets,
    validate_forecasts,
)
from gridsense.features.build import _weather_features, drop_untrainable
from gridsense.schemas import WEATHER_FC


def payload(day="2025-07-01", periods=24, variables=VARIABLES):
    times = pd.date_range(day, periods=periods, freq="h", tz="UTC")
    hourly = {"time": (times.as_unit("s").asi8).tolist()}
    units = {"time": "unixtime"}
    for variable, (_, unit) in variables.items():
        for offset in range(1, MAX_OFFSET + 1):
            key = f"{variable}_previous_day{offset}"
            hourly[key] = [float(offset)] * len(times)
            units[key] = unit
    return {"utc_offset_seconds": 0, "hourly": hourly, "hourly_units": units}


def parse(p, variables=VARIABLES):
    return parse_forecasts(p, "bucuresti", pd.Timestamp("2026-11-07", tz="UTC"), variables)


def test_uses_older_offsets_not_the_target_horizon_naively():
    out = parse(payload())
    issue = (out.issue_date + pd.Timedelta(hours=config.ISSUE_HOUR)).dt.tz_localize(
        config.LOCAL_TZ
    ).dt.tz_convert("UTC")
    supported = out.source_offset_days.le(MAX_OFFSET)
    assert out.loc[supported, "assumed_available_by_utc"].le(issue[supported]).all()
    assert (out.loc[supported, "source_offset_days"] > out.loc[supported, "lead_days"]).all()
    np.testing.assert_array_equal(out.loc[supported, "temp_c"].to_numpy(),
                                  out.loc[supported, "source_offset_days"].to_numpy())
    assert out.loc[~supported, list(WEATHER_FC)[4:]].isna().all().all()
    assert out.loc[out.lead_days.eq(7), list(WEATHER_FC)[4:]].isna().all().all()
    assert out.dtypes.astype(str)[list(WEATHER_FC)].to_dict() == WEATHER_FC


@pytest.mark.parametrize("day", ["2025-03-30", "2025-10-26", "2025-01-01"])
def test_cutoff_and_local_horizons_across_dst(day):
    out = parse(payload(day, periods=48))
    validate_forecasts(out)
    assert len(out) == 48 * len(config.HORIZONS_DAYS)
    local = out.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    assert (local - out.issue_date).eq(pd.to_timedelta(out.lead_days, unit="D")).all()


def test_missing_archive_values_are_not_filled_with_other_offsets():
    p = payload()
    for offset in range(1, MAX_OFFSET + 1):
        p["hourly"][f"shortwave_radiation_previous_day{offset}"] = [None] * 24
    out = parse(p)
    assert out.ghi_wm2.isna().all()
    assert out.temp_c.notna().any()


def test_radiation_is_aligned_to_the_delivery_hour_not_the_previous_hour():
    p = payload()
    for offset in range(1, MAX_OFFSET + 1):
        p["hourly"][f"shortwave_radiation_previous_day{offset}"] = list(range(24))
    out = parse(p)
    h1 = out[out.lead_days.eq(1)]
    assert h1.ghi_wm2.iloc[0] == 1.0
    assert pd.isna(h1.ghi_wm2.iloc[-1])  # no t+1 forecast; no extrapolation


def test_impossible_cloud_values_are_masked_not_clipped():
    p = payload()
    for offset in range(1, MAX_OFFSET + 1):
        p["hourly"][f"cloud_cover_previous_day{offset}"] = [101.0] * 24
    out = parse(p)
    assert out.cloud_cover_pct.isna().all()
    assert out.source_invalid_values.gt(0).any()
    assert out.temp_c.notna().any()


def test_rejects_wrong_units():
    p = payload()
    p["hourly_units"]["wind_speed_100m_previous_day2"] = "km/h"
    with pytest.raises(ValueError, match="units"):
        parse(p)


def test_rejects_non_utc_or_duplicate_times():
    p = payload()
    p["utc_offset_seconds"] = 3600
    with pytest.raises(ValueError, match="UTC"):
        parse(p)
    p = payload()
    p["hourly"]["time"][1] = p["hourly"]["time"][0]
    with pytest.raises(ValueError, match="unique UTC hours"):
        parse(p)


def test_feature_join_rejects_after_cutoff_weather():
    out = parse(payload())
    idx = out.index[out.temp_c.notna()][0]
    out.loc[idx, "assumed_available_by_utc"] += pd.Timedelta(days=2)
    with pytest.raises(ValueError, match="issue cutoff"):
        _weather_features(out)


def test_future_offset_changes_cannot_change_selected_forecasts():
    p = payload()
    out = parse(p)
    for variable in VARIABLES:
        p["hourly"][f"{variable}_previous_day1"] = [50.0] * 24
    pd.testing.assert_frame_equal(out, parse(p))


def test_offset_boundary_and_month_ranges():
    issue = pd.Series(pd.to_datetime(["2025-01-01T08:00Z"] * 2))
    target = issue + pd.to_timedelta([48 - PUBLICATION_BUFFER_HOURS,
                                    49 - PUBLICATION_BUFFER_HOURS], unit="h")
    assert select_offsets(target, issue).tolist() == [2, 3]
    ranges = list(_month_ranges(pd.Timestamp("2025-01-31", tz="UTC"),
                                pd.Timestamp("2025-03-01", tz="UTC")))
    assert [(str(a), str(b)) for a, b in ranges] == [
        ("2025-01-31", "2025-01-31"), ("2025-02-01", "2025-02-28")
    ]


def extra_payload(day="2025-07-01"):
    p = payload(day, variables=EXTRA_VARIABLES)
    for offset in range(1, MAX_OFFSET + 1):
        p["hourly"][f"surface_pressure_previous_day{offset}"] = [1000.0 + offset] * 24
        p["hourly"][f"precipitation_previous_day{offset}"] = list(map(float, range(24)))
        p["hourly"][f"wind_direction_10m_previous_day{offset}"] = [350.0 if offset % 2 else 10.0] * 24
    return p


def test_extra_variables_use_the_same_offsets_and_preceding_hour_alignment():
    core, extra = parse(payload()), parse(extra_payload(), EXTRA_VARIABLES)
    validate_forecasts(extra)
    pd.testing.assert_series_equal(core.source_offset_days, extra.source_offset_days)
    supported = extra.source_offset_days.le(MAX_OFFSET)
    assert extra.loc[supported, "pressure_hpa"].sub(1000).eq(extra.loc[supported, "source_offset_days"]).all()
    h1 = extra[extra.lead_days.eq(1)]
    assert h1.precip_mm.iloc[0] == 1.0  # API precipitation at t+1 is the delivery hour [t, t+1)
    assert extra.loc[~supported, ["humidity_pct", "precip_mm"]].isna().all().all()


def test_merge_extra_keeps_core_rows_and_leaves_unarchived_dates_missing():
    core = pd.concat([parse(payload("2025-07-01")), parse(payload("2025-07-02"))], ignore_index=True)
    extra = parse(extra_payload("2025-07-02"), EXTRA_VARIABLES)
    merged = merge_extra(core, extra.assign(request_sha256="r", raw_sha256="h"))
    assert len(merged) == len(core)
    pd.testing.assert_frame_equal(merged[core.columns], core)
    day = merged.target_ts_utc.dt.strftime("%Y-%m-%d")
    assert merged.loc[day.eq("2025-07-01"), "humidity_pct"].isna().all()
    assert merged.loc[day.eq("2025-07-02"), "humidity_pct"].notna().any()
    bad = extra.assign(request_sha256="r", raw_sha256="h", source_offset_days=extra.source_offset_days + 1)
    with pytest.raises(ValueError, match="same archived offsets"):
        merge_extra(core, bad)


def test_extra_weather_features_encode_direction_as_a_unit_vector():
    merged = merge_extra(parse(payload()), parse(extra_payload(), EXTRA_VARIABLES).assign(
        request_sha256="r", raw_sha256="h"))
    plain = _weather_features(merged)
    assert not plain.filter(regex="humidity|winddir").columns.any()
    features = _weather_features(merged, extra=True)
    row = features.dropna(subset=["f_winddir_cos_bucuresti"]).iloc[0]
    assert row.f_winddir_cos_bucuresti == pytest.approx(np.cos(np.deg2rad(10)))
    assert abs(row.f_winddir_sin_bucuresti) == pytest.approx(np.sin(np.deg2rad(10)))
    assert {"f_humidity_mean", "f_precip_mean", "f_pressure_mean", "f_wind10_mean"} <= set(features)
    pd.testing.assert_frame_equal(features[plain.columns], plain)
    with pytest.raises(ValueError, match="extra variables"):
        _weather_features(parse(payload()), extra=True)


def test_drop_untrainable_removes_features_without_training_values():
    ts = pd.Series([config.TRAIN_START + pd.Timedelta(days=1), config.VAL_START + pd.Timedelta(days=1)])
    table = pd.DataFrame({"target_ts_utc": ts.dt.tz_convert("UTC"), "f_ok": [1.0, 2.0],
                          "f_test_only": [np.nan, 5.0], "y_price": [1.0, 2.0]})
    out, empty = drop_untrainable(table)
    assert empty == ["f_test_only"]
    assert list(out.columns) == ["target_ts_utc", "f_ok", "y_price"]