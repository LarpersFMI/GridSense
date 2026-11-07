import pandas as pd
import pytest

from gridsense.data.compare_historical_capacity import compare
from gridsense.data.historical_unit_reference import COLS, normalize


def test_inventory_accepts_missing_generation_identifier_but_rejects_duplicate_keys():
    row = dict.fromkeys(COLS, "")
    row.update(country="Romania", eic_p="P1", capacity_p="100")
    result = normalize(pd.DataFrame([row]))
    assert len(result) == 1
    assert pd.isna(result.loc[0, "generation_unit_code"])
    with pytest.raises(ValueError, match="Duplicate"):
        normalize(pd.DataFrame([row, row]))


def test_comparison_counts_only_valid_references_and_rejects_conflicting_old_values():
    start = pd.Timestamp("2024-01-01", tz="UTC")
    events = pd.DataFrame({"asset_code": ["A", "B"], "segment_start_utc": [start, start]})
    reference = pd.DataFrame({"code": ["A", "B"], "capacity": [100., 50.],
                              "valid_from_utc": [start, start + pd.Timedelta(days=1)],
                              "valid_to_utc": pd.to_datetime([None, None], utc=True)})
    historical = pd.DataFrame({"code": ["A", "B"], "old_capacity": [90., 50.]})
    result = compare(events, reference, historical, "code", "capacity", "old_capacity")
    assert result["segments"] == 2
    assert result["capacity_pairs_compared"] == 1
    assert result["different_capacity_segments"] == 1
    conflicting = pd.concat([historical, pd.DataFrame({"code": ["A"], "old_capacity": [80.]})])
    with pytest.raises(ValueError, match="Conflicting"):
        compare(events, reference, conflicting, "code", "capacity", "old_capacity")
