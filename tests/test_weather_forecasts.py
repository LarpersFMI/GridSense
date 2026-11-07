import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.data.weather import (
    MAX_OFFSET,
    PUBLICATION_BUFFER_HOURS,
    VARIABLES,
    _month_ranges,
    parse_forecasts,
    select_offsets,
    validate_forecasts,
)
from gridsense.features.build import _weather_features
from gridsense.schemas import WEATHER_FC


def payload(day="2025-07-01", periods=24):
    times = pd.date_range(day, periods=periods, freq="h", tz="UTC")
    hourly = {"time": (times.as_unit("s").asi8).tolist()}
    units = {"time": "unixtime"}
    for variable, (_, unit) in VARIABLES.items():
        for offset in range(1, MAX_OFFSET + 1):
            key = f"{variable}_previous_day{offset}"
            hourly[key] = [float(offset)] * len(times)
            units[key] = unit
    return {"utc_offset_seconds": 0, "hourly": hourly, "hourly_units": units}


def parse(p):
    return parse_forecasts(p, "bucuresti", pd.Timestamp("2026-11-07", tz="UTC"))


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