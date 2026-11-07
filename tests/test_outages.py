import pandas as pd
import pytest

from gridsense import config
from gridsense.data import entsoe_files, outages

HEADER = (
    "MRID\tUpdateTime\tStartTS\tEndTS\tMapCode\tProductionType\t"
    "InstalledCapacity\tAvailableCapacity\tStatus"
)


def export(tmp_path, lines):
    path = tmp_path / "2025_06_UnavailabilityOfGenerationUnits_15.1.A_B.csv"
    path.write_text("\n".join([HEADER, *("\t".join(line) for line in lines)]) + "\n")
    return outages.read_export(path)


def rows(issue, targets):
    return pd.DataFrame(
        {
            "issue_ts": pd.Timestamp(issue, tz="UTC"),
            "target_ts_utc": pd.to_datetime(targets, utc=True).astype("datetime64[ns, UTC]"),
        }
    )


def test_read_export_filters_romania_and_maps_fuel(tmp_path):
    events = export(
        tmp_path,
        [
            ["a", "2025-06-01 08:00", "2025-06-03 00:00", "2025-06-04 00:00", "RO", "Nuclear",
             "700", "0", "Active"],
            ["b", "2025-06-01 08:00", "2025-06-03 00:00", "2025-06-04 00:00", "HU", "Nuclear",
             "500", "0", "Active"],
        ],
    )
    assert events["message_id"].tolist() == ["a"]
    assert events.loc[0, ["fuel", "unavailable_mw"]].tolist() == ["nuclear", 700.0]
    assert str(events["start_utc"].dtype) == "datetime64[ns, UTC]"


def test_only_versions_published_by_issue_time_count(tmp_path):
    events = export(
        tmp_path,
        [
            # Planned on 1 June, cancelled on 2 June at noon.
            ["a", "2025-06-01 08:00", "2025-06-03 00:00", "2025-06-04 00:00", "RO", "Nuclear",
             "700", "0", "Active"],
            ["a", "2025-06-02 12:00", "2025-06-03 00:00", "2025-06-04 00:00", "RO", "Nuclear",
             "700", "0", "Cancelled"],
            # Published after the first issue time; half of the 00:00 hour is affected.
            ["b", "2025-06-02 09:00", "2025-06-03 00:30", "2025-06-03 02:00", "RO",
             "Fossil Gas", "400", "100", "Active"],
        ],
    )
    targets = ["2025-06-03 00:00", "2025-06-03 01:00", "2025-06-03 02:00"]
    table = pd.concat(
        [rows("2025-06-02 08:00", targets), rows("2025-06-02 10:00", targets),
         rows("2025-06-02 13:00", targets)],
        ignore_index=True,
    )
    out = outages.offline_mw_as_of(events, table)
    nuclear, fossil = out["f_offline_mw_nuclear"], out["f_offline_mw_fossil"]
    assert nuclear.tolist() == [700, 700, 700, 700, 700, 700, 0, 0, 0]
    assert fossil.tolist() == [0, 0, 0, 150, 300, 0, 150, 300, 0]
    assert (out["f_offline_mw_total"] == nuclear + fossil).all()


def test_read_export_reports_missing_columns(tmp_path):
    path = tmp_path / "2025_06_x.csv"
    path.write_text("MapCode,StartTS\nRO,2025-06-01\n")
    with pytest.raises(ValueError, match="no column for message_id"):
        outages.read_export(path)


def test_select_monthly_files():
    names = ["2024_12_X.csv", "2025_01_X.csv", "2025_03_X.csv", "notes.txt", "2025_02_X.csv"]
    assert entsoe_files.select_monthly(names, "2025-01", "2025-02") == [
        "2025_01_X.csv",
        "2025_02_X.csv",
    ]


def test_sync_rejects_unsafe_folder():
    with pytest.raises(ValueError, match="Invalid dataset folder"):
        entsoe_files.sync_folder("../etc", "2025-01", "2025-02")


def test_romanian_rows_keeps_values_as_text():
    payload = (
        "DateTime(UTC)\tAreaCode\tAreaMapCode\tMaximumLoadForecast[MW]\n"
        f"2024-01-01 22:00:00\t{config.BIDDING_ZONE}\tRO\t6300.0\n"
        "2024-01-01 22:00:00\t10YHU-MAVIR----U\tHU\t5000.0\n"
    ).encode()
    rows = entsoe_files.romanian_rows(payload, "x.csv")
    assert rows["MaximumLoadForecast[MW]"].tolist() == ["6300.0"]
