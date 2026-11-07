import pandas as pd
import pytest

from gridsense import config
from gridsense.data import build_file_library, refresh_checks


@pytest.mark.parametrize(("day", "count"), [("2025-03-30", 23), ("2025-10-26", 25)])
def test_hour_coverage_accepts_dst_and_rejects_gaps_and_duplicates(day, count):
    local = pd.Timestamp(day)
    expected = (
        pd.date_range(
            local.tz_localize(config.LOCAL_TZ),
            (local + pd.Timedelta(days=1)).tz_localize(config.LOCAL_TZ),
            freq="h",
            inclusive="left",
        )
        .tz_convert("UTC")
        .as_unit("ns")
    )
    hourly = pd.DataFrame({"ts_utc": expected})
    assert len(hourly) == count
    assert (
        refresh_checks.hour_coverage(hourly, expected, "prices", require_complete=True)[
            "missing_hours"
        ]
        == 0
    )
    assert refresh_checks.hour_coverage(hourly.iloc[1:], expected, "load")["missing_hours"] == 1
    with pytest.raises(ValueError, match="1 missing hours"):
        refresh_checks.hour_coverage(hourly.iloc[1:], expected, "prices", require_complete=True)
    with pytest.raises(ValueError, match="conflicting records"):
        refresh_checks.hour_coverage(pd.concat([hourly, hourly.iloc[:1]]), expected, "prices")


@pytest.mark.parametrize("day", ["2025-03-30", "2025-10-26"])
def test_asof_cutoff_uses_bucharest_clock_and_rejects_late_or_unknown_update(tmp_path, day):
    local = pd.Timestamp(day)
    issue = (
        (local + pd.Timedelta(hours=config.ISSUE_HOUR))
        .tz_localize(config.LOCAL_TZ)
        .tz_convert("UTC")
    )
    target = (local + pd.Timedelta(days=1)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    path = tmp_path / "load_fc_week_ahead_asof.parquet"
    row = pd.DataFrame(
        {
            "issue_ts": [issue],
            "target_ts_utc": [target],
            "horizon_days": [1],
            "load_fc_min_mw": [4000.0],
            "load_fc_max_mw": [8000.0],
            "load_fc_updated_at_utc": [issue],
        }
    )
    row.to_parquet(path)
    assert refresh_checks.check_handoff(tmp_path) == {"load_fc_week_ahead_asof": 1}
    for timestamp in (issue + pd.Timedelta(seconds=1), pd.NaT):
        row["load_fc_updated_at_utc"] = pd.to_datetime([timestamp], utc=True)
        row.to_parquet(path)
        with pytest.raises(ValueError, match="lacks evidence by the 10:00 issue cutoff"):
            refresh_checks.check_handoff(tmp_path)


def test_failed_staged_check_leaves_destination_intact(tmp_path, monkeypatch):
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    load = pd.DataFrame({"country_code": ["RO"], "ts_utc": [start]})
    features = pd.DataFrame({"issue_ts": [start], "target_ts_utc": [start], "horizon_days": [1]})
    tables = {
        f"{build_file_library.SOURCE}/actual_load": (load, ["country_code", "ts_utc"]),
        "regional_load_hourly": (load, ["country_code", "ts_utc"]),
        "regional_market_features": (features, list(features.columns)),
    }
    integration = {"load_coverage_by_country": {}}
    monkeypatch.setattr(
        build_file_library, "build_tables", lambda *_: (tables, {}, {"RO": {}}, integration)
    )

    def reject(staged, *_):
        assert (staged / "regional_load_hourly.parquet").is_file()
        raise ValueError("test staged validation failure")

    monkeypatch.setattr(refresh_checks, "check_market_refresh", reject)
    prior = tmp_path / "regional_load_hourly.parquet"
    prior.write_bytes(b"preserve existing output")
    with pytest.raises(ValueError, match="staged validation failure"):
        build_file_library.build(tmp_path, tmp_path, replace_existing=True)
    assert prior.read_bytes() == b"preserve existing output"
    assert list(tmp_path.iterdir()) == [prior]
