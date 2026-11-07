import pandas as pd
import pytest

from gridsense.data.outage_quality import find_exceptions


def fixtures():
    start = pd.Timestamp("2024-01-01 00:00Z")
    outages = pd.DataFrame({
        "area_code": ["RO", "RO"], "instance_code": ["event", "event"], "version": [1, 1],
        "asset_code": ["unit", "unit"], "asset_type": ["PRODUCTION", "PRODUCTION"],
        "segment_start_utc": [start, start + pd.Timedelta(hours=1)],
        "segment_end_utc": [start + pd.Timedelta(hours=1), start + pd.Timedelta(hours=2)],
        "published_at_utc": [start - pd.Timedelta(days=1), start - pd.Timedelta(days=2)],
        "available_capacity_mw": [701.0, None],
    })
    production = pd.DataFrame({
        "production_unit_code": ["unit"], "installed_capacity_mw": [700.0],
        "status": ["COMMISSIONED"], "valid_from_utc": [start - pd.Timedelta(days=10)],
        "valid_to_utc": [start + pd.Timedelta(minutes=30)],
        "updated_at_utc": [start + pd.Timedelta(days=100)],
    })
    generation = pd.DataFrame({
        "generation_unit_code": pd.Series(dtype="string"),
        "generation_installed_capacity_mw": pd.Series(dtype="float64"),
        "generation_unit_status": pd.Series(dtype="string"),
        "valid_from_utc": pd.Series(dtype="datetime64[ns, UTC]"),
        "valid_to_utc": pd.Series(dtype="datetime64[ns, UTC]"),
        "updated_at_utc": pd.Series(dtype="datetime64[ns, UTC]"),
    })
    return outages, production, generation


def test_exception_flags_preserve_source_timestamps_and_dont_clip():
    events, production, generation = fixtures()
    result = find_exceptions(events, production, generation)
    assert len(result) == 2
    first, second = result.iloc[0], result.iloc[1]
    assert first.available_exceeds_installed and first.segment_crosses_validity_end
    assert first.available_capacity_mw == 701 and first.reference_installed_mw == 700
    assert first.reference_updated_at_utc > first.published_at_utc
    assert second.missing_available_capacity and second.missing_reference
    assert result.multiple_publication_times.all()


def test_ambiguous_reference_is_not_selected_and_duplicate_events_fail():
    events, production, generation = fixtures()
    result = find_exceptions(events, pd.concat([production, production]), generation)
    assert result.iloc[0].ambiguous_reference
    assert pd.isna(result.iloc[0].reference_installed_mw)
    with pytest.raises(ValueError, match="unique"):
        find_exceptions(pd.concat([events, events.iloc[:1]]), production, generation)
