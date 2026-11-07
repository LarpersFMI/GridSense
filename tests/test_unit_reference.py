import pandas as pd
import pytest

from gridsense import config
from gridsense.data.unit_reference import normalize


def production_rows():
    return pd.DataFrame(
        {
            "ProductionUnitCode": ["unit1", "foreign"],
            "ProductionUnitName": ["Unit 1", "Foreign"],
            "ValidityPeriodStart(UTC)": ["2023-01-01 00:00:00"] * 2,
            "ValidityPeriodEnd(UTC)": ["", ""],
            "Status": ["COMMISSIONED"] * 2,
            "ProductionType": ["Nuclear"] * 2,
            "ProductionUnitLocation": ["internal"] * 2,
            "InstalledCapacity[MW]": ["700", "100"],
            "AreaCode": [config.BIDDING_ZONE, "foreign"],
            "AreaMapCode": ["RO", "XX"],
            "VoltageLevel[kV]": ["400", "400"],
            "UpdateTime(UTC)": ["2026-11-07 15:00:51"] * 2,
        }, dtype="string"
    )


def test_reference_preserves_validity_and_late_update_without_imputation():
    result = normalize(production_rows(), "production_units")
    assert len(result) == 1
    assert result.installed_capacity_mw.iloc[0] == 700
    assert pd.isna(result.valid_to_utc.iloc[0])
    assert result.updated_at_utc.iloc[0] == pd.Timestamp("2026-11-07 15:00:51", tz="UTC")


def test_reference_rejects_duplicate_keys_and_invalid_capacity():
    rows = production_rows().iloc[:1]
    with pytest.raises(ValueError, match="duplicate"):
        normalize(pd.concat([rows, rows]), "production_units")
    rows = rows.copy()
    rows.loc[rows.index[0], "InstalledCapacity[MW]"] = "-1"
    with pytest.raises(ValueError, match="invalid installed_capacity_mw"):
        normalize(rows, "production_units")


def test_outage_reference_audit_detects_ambiguous_matches_and_late_updates():
    from gridsense.data.audit_unit_reference import audit

    reference = normalize(production_rows(), "production_units")
    start = pd.Timestamp("2024-01-01", tz="UTC")
    outages = pd.DataFrame(
        {
            "asset_type": ["PRODUCTION", "PRODUCTION"],
            "asset_code": ["unit1", "unknown"],
            "segment_start_utc": [start, start],
            "segment_end_utc": [start + pd.Timedelta(hours=1)] * 2,
            "published_at_utc": [start, start],
            "available_capacity_mw": [701.0, None],
        }
    )
    generation = pd.DataFrame(
        {
            "generation_unit_code": pd.Series(dtype="string"),
            "valid_from_utc": pd.Series(dtype="datetime64[ns, UTC]"),
            "valid_to_utc": pd.Series(dtype="datetime64[ns, UTC]"),
            "updated_at_utc": pd.Series(dtype="datetime64[ns, UTC]"),
            "generation_installed_capacity_mw": pd.Series(dtype="float64"),
        }
    )
    result = audit(outages, pd.concat([reference, reference]), generation)["PRODUCTION"]
    assert result["with_multiple_valid_capacity_matches"] == 1
    assert result["with_no_valid_capacity_match"] == 1
    assert result["with_capacity_updated_by_outage_publication"] == 0
    assert result["available_exceeds_matched_installed_capacity"] == 1
    assert result["missing_available_capacity"] == 1
