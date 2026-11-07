import hashlib

import pandas as pd
import pytest

from gridsense.data.build_file_library import (
    complete_hours,
    install_staged,
    read_export,
    updated_by_next_issue,
)


def test_price_deduplication_preserves_market_sequences(tmp_path):
    folder = tmp_path / "prices"
    folder.mkdir()
    path = folder / "month.csv.gz"
    start = pd.Timestamp("2026-10-01T00:00:00Z")
    end = start + pd.Timedelta(hours=1)
    rows = pd.DataFrame(
        {
            "DateTime(UTC)": ["2026-10-01 00:00:00"] * 3,
            "ResolutionCode": ["PT15M"] * 3,
            "AreaCode": ["10Y1001A1001A82H"] * 3,
            "AreaMapCode": ["DE_LU"] * 3,
            "InstanceCode": ["later", "earlier", "second_sequence"],
            "ContractType": ["Day-ahead"] * 3,
            "Sequence": ["1", "1", "2"],
            "Currency": ["EUR"] * 3,
            "Price[Currency/MWh]": [40, 40, 50],
            "UpdateTime(UTC)": [
                "2026-09-30 12:30:00",
                "2026-09-30 12:00:00",
                "2026-09-30 12:00:00",
            ],
        }
    )
    rows.to_csv(path, sep="\t", index=False)
    prices, stats = read_export(tmp_path, "prices", start, end)
    assert prices["instance_code"].tolist() == ["earlier", "second_sequence"]
    assert stats["duplicates_removed"] == 1
    assert stats["source_sha256"][f"{tmp_path.name}/prices/month.csv.gz"] == hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    rows.loc[0, "Price[Currency/MWh]"] = 41
    rows.to_csv(path, sep="\t", index=False)
    with pytest.raises(ValueError, match="Conflicting day-ahead quotes"):
        read_export(tmp_path, "prices", start, end)


def test_complete_hours_and_issue_cutoff_use_all_four_quarters():
    # The following day starts standard time; 10:00 Bucharest is 08:00 UTC.
    cutoff = pd.Timestamp("2026-10-25T08:00:00Z")
    rows = pd.DataFrame(
        {
            "ts_utc": pd.date_range("2026-10-24T12:00:00Z", periods=7, freq="15min"),
            "resolution": "PT15M",
            "load_mw": [1.0, 3.0, 5.0, 7.0, 8.0, 9.0, 10.0],
            "updated_at_utc": cutoff,
        }
    )
    hourly = complete_hours(rows, "load_mw")
    assert hourly["load_mw"].tolist() == [4.0]
    assert updated_by_next_issue(hourly).tolist() == [True]

    rows.loc[3, "updated_at_utc"] = cutoff + pd.Timedelta(seconds=1)
    assert updated_by_next_issue(complete_hours(rows, "load_mw")).tolist() == [False]


def test_native_hourly_load_preserves_gaps():
    rows = pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2026-10-25T00:00Z", "2026-10-25T02:00Z"]),
            "resolution": "PT60M",
            "load_mw": [5000.0, 5100.0],
            "updated_at_utc": pd.Timestamp("2026-10-25T04:00:00Z"),
        }
    )
    actual = complete_hours(rows, "load_mw", resolution="PT60M")
    pd.testing.assert_frame_equal(actual, rows.drop(columns="resolution"))
    with pytest.raises(ValueError, match="conflicting records"):
        complete_hours(pd.concat([rows, rows.iloc[:1]]), "load_mw", resolution="PT60M")


def test_staged_install_checks_all_outputs_before_writing(tmp_path):
    staged = tmp_path / "staged"
    dest = tmp_path / "dest"
    staged.mkdir()
    dest.mkdir()
    (dest / "a").write_text("old a")
    (dest / "b").write_text("old b")
    (staged / "a").write_text("new a")
    (staged / "b").write_text("old b")

    with pytest.raises(ValueError, match="No outputs written"):
        install_staged(staged, dest, ["b", "a"])
    assert (dest / "a").read_text() == "old a"
    assert (dest / "b").read_text() == "old b"
    assert (staged / "b").exists()

    install_staged(staged, dest, ["b", "a"], replace_existing=True)
    assert (dest / "a").read_text() == "new a"
    assert (dest / "b").read_text() == "old b"
