import pandas as pd

from gridsense.data.load_forecast import parse_week_ahead
from gridsense.features.build import _week_ahead_load_features
from gridsense.schemas import LOAD_FC_WEEK_AHEAD


def test_parse_week_ahead_keeps_romanian_week_ahead_rows():
    raw = pd.DataFrame(
        {
            "DateTime(UTC)": ["2024-01-07 22:00:00", "2024-01-07 22:00:00", "2024-01-07 22:00:00"],
            "ResolutionCode": ["P1D", "P1D", "P1D"],
            "AreaMapCode": ["RO", "RO", "HU"],
            "ContractType": ["Week-ahead", "Month-ahead", "Week-ahead"],
            "MinimumLoadForecast[MW]": ["5000", "1", "2"],
            "MaximumLoadForecast[MW]": ["7000", "1", "2"],
            "UpdateTime(UTC)": ["2024-01-04 09:00:00"] * 3,
        }
    )
    out = parse_week_ahead(raw)
    assert out.dtypes.astype(str).to_dict() == LOAD_FC_WEEK_AHEAD
    # 22:00 UTC on Sunday is Monday 00:00 in Bucharest.
    assert out["target_date"].tolist() == [pd.Timestamp("2024-01-08")]
    assert out[["load_fc_min_mw", "load_fc_max_mw"]].iloc[0].tolist() == [5000, 7000]


def test_week_ahead_load_only_after_saturday_before_target_week():
    load_fc = pd.DataFrame(
        {
            "target_date": pd.to_datetime(["2024-01-08", "2024-01-14"]),
            "load_fc_min_mw": [5000.0, 4000.0],
            "load_fc_max_mw": [7000.0, 6000.0],
        }
    )
    # Target week Mon 2024-01-08..Sun 2024-01-14; forecast published Thursday 2024-01-04.
    rows = pd.DataFrame(
        {
            "issue_date": pd.to_datetime(["2024-01-05", "2024-01-06", "2024-01-07", "2024-01-13"]),
            "target_date": pd.to_datetime(["2024-01-08", "2024-01-08", "2024-01-14", "2024-01-14"]),
        }
    )
    out = _week_ahead_load_features(rows, load_fc)
    assert out["f_load_fc_max"].isna().tolist() == [True, False, False, False]
    assert out["f_load_fc_min"].tolist()[1:] == [5000, 4000, 4000]
