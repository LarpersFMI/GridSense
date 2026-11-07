import pandas as pd
import pytest

from gridsense import config
from gridsense.data.week_ahead_asof import build_asof, main


def keys():
    return pd.DataFrame(
        {
            "issue_ts": pd.to_datetime(["2025-01-01 08:00Z", "2025-01-02 08:00Z"]),
            "target_ts_utc": pd.to_datetime(["2025-01-03 10:00Z", "2025-01-03 10:00Z"]),
            "horizon_days": [2, 1],
        }
    )


def source():
    return pd.DataFrame(
        {
            "area_code": [config.BIDDING_ZONE] * 3,
            "contract_type": ["Week-ahead"] * 3,
            "resolution": ["P1D"] * 3,
            "ts_utc": pd.to_datetime(["2025-01-02 22:00Z"] * 3),
            "updated_at_utc": pd.to_datetime(
                ["2025-01-01 08:00Z", "2025-01-02 07:00Z", "2025-01-02 09:00Z"]
            ),
            "min_load_mw": [100., 200., 300.],
            "max_load_mw": [150., 250., 350.],
        }
    )


def test_latest_revision_at_or_before_issue_and_row_order():
    result = build_asof(keys().iloc[::-1], source())
    assert result.load_fc_min_mw.tolist() == [200., 100.]
    assert (result.load_fc_updated_at_utc <= result.issue_ts).all()


def test_future_revision_is_missing():
    result = build_asof(keys().iloc[:1], source().iloc[1:])
    assert pd.isna(result.load_fc_min_mw.iloc[0])
    assert pd.isna(result.load_fc_updated_at_utc.iloc[0])


def test_duplicate_keys_and_conflicting_vintages_rejected():
    with pytest.raises(ValueError, match="unique"):
        build_asof(pd.concat([keys(), keys().iloc[:1]]), source())
    bad = source().iloc[[0, 0]].copy()
    bad.iloc[1, bad.columns.get_loc("min_load_mw")] = 101.
    with pytest.raises(ValueError, match="Conflicting"):
        build_asof(keys(), bad)


def test_refresh_requires_review_and_preserves_both_existing_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_MODE", "real")
    inputs = tmp_path / "entsoe_file_library"
    inputs.mkdir()
    training_path = tmp_path / "training_table.parquet"
    keys().to_parquet(training_path, index=False)
    source().to_parquet(inputs / "week_ahead_load.parquet", index=False)
    main([])
    output = tmp_path / "load_fc_week_ahead_asof.parquet"
    manifest = tmp_path / "load_fc_week_ahead_asof_manifest.json"
    before = (output.read_bytes(), manifest.read_bytes())

    keys().assign(unrelated=[1, 2]).to_parquet(training_path, index=False)
    with pytest.raises(ValueError, match="No outputs written"):
        main([])
    assert (output.read_bytes(), manifest.read_bytes()) == before
    main(["--replace-existing"])
    assert output.read_bytes() == before[0]
    assert manifest.read_bytes() != before[1]
