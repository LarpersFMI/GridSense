import pandas as pd
import pytest

from gridsense import config
from gridsense.data.renewable_generation_asof import build_handoff


def sample(day, issue):
    start = pd.Timestamp(day, tz=config.LOCAL_TZ).tz_convert("UTC")
    end = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    periods = pd.date_range(start, end, freq="15min", inclusive="left")
    issue = pd.Timestamp(issue, tz="UTC")
    target = (issue.tz_convert(config.LOCAL_TZ).tz_localize(None).normalize() + pd.Timedelta(days=1, hours=12)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    keys = pd.DataFrame({"issue_ts": [issue], "target_ts_utc": [target], "horizon_days": [1]})
    generation = pd.concat(
        [pd.DataFrame({"ts_utc": periods, "updated_at_utc": periods + pd.Timedelta(minutes=16),
                       "production_type": fuel, "generation_mw": float(value),
                       "resolution": "PT15M", "area_code": config.BIDDING_ZONE})
         for fuel, value in [("Solar", 10), ("Wind Onshore", 20)]], ignore_index=True
    )
    return keys, generation


@pytest.mark.parametrize(
    ("day", "issue", "hours"),
    [("2025-03-30", "2025-03-31 07:00", 23), ("2025-10-26", "2025-10-27 08:00", 25)],
)
def test_complete_dst_day_and_exact_cutoff(day, issue, hours):
    keys, source = sample(day, issue)
    source.loc[source.index[-1], "updated_at_utc"] = keys.issue_ts.iloc[0]
    result = build_handoff(keys, source).iloc[0]
    assert result.expected_hours == result.solar_known_hours == result.wind_known_hours == hours
    assert result.solar_daily_mw == 10 and result.wind_daily_mw == 20
    assert result.wind_updated_at_utc == keys.issue_ts.iloc[0]


def test_late_quarter_or_missing_hour_cannot_produce_partial_daily_statistics():
    keys, source = sample("2025-03-30", "2025-03-31 07:00")
    source.loc[source.index[-1], "updated_at_utc"] = keys.issue_ts.iloc[0] + pd.Timedelta(seconds=1)
    source = source.drop(source.index[0])
    result = build_handoff(keys, source).iloc[0]
    assert pd.isna(result.wind_daily_mw) and pd.isna(result.solar_daily_mw)
    assert result.wind_known_hours == result.solar_known_hours == 22
    assert pd.isna(result.wind_updated_at_utc)


def test_duplicate_keys_and_invalid_timestamps_are_rejected():
    keys, source = sample("2025-03-30", "2025-03-31 07:00")
    with pytest.raises(ValueError, match="unique"):
        build_handoff(pd.concat([keys, keys]), source)
    with pytest.raises(ValueError, match="Duplicate"):
        build_handoff(keys, pd.concat([source, source.iloc[:1]]))
    source.loc[0, "updated_at_utc"] = source.loc[0, "ts_utc"]
    with pytest.raises(ValueError, match="before its delivery"):
        build_handoff(keys, source)
