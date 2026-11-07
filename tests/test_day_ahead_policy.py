"""Synthetic policy-only checks; do not interpret as electricity-market results."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridsense import config

_root = Path(__file__).parents[1] / "experiments"
if "experiments" not in sys.modules:
    _package_spec = importlib.util.spec_from_file_location(
        "experiments", _root / "__init__.py", submodule_search_locations=[str(_root)])
    assert _package_spec is not None and _package_spec.loader is not None
    _package = importlib.util.module_from_spec(_package_spec)
    sys.modules["experiments"] = _package
    _package_spec.loader.exec_module(_package)
_spec = importlib.util.spec_from_file_location("experiments.day_ahead_policy", _root / "day_ahead_policy.py")
assert _spec is not None and _spec.loader is not None
experiment = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = experiment
_spec.loader.exec_module(experiment)


def evidence():
    return pd.DataFrame([
        {"predictor": "hourly_d1", "max_length": 2, "tau": 0.9, "accepted": True,
         "announced_hours": 90, "worst_month_cancellation": 0.0, "cancellation_rate": 0.0,
         "day_hit_lower_bound": 0.93},
        {"predictor": "slot_d1", "max_length": 2, "tau": 0.8, "accepted": True,
         "announced_hours": 120, "worst_month_cancellation": 0.05, "cancellation_rate": 0.02,
         "day_hit_lower_bound": 0.91},
        {"predictor": "hourly_pooled", "max_length": 2, "tau": 0.9, "accepted": True,
         "announced_hours": 150, "worst_month_cancellation": 0.0, "cancellation_rate": 0.0,
         "day_hit_lower_bound": 0.99},
        {"predictor": "slot_d1", "max_length": 4, "tau": 0.9, "accepted": True,
         "announced_hours": 150, "worst_month_cancellation": 0.0, "cancellation_rate": 0.0,
         "day_hit_lower_bound": 0.99},
    ])


def test_safety_precedes_volume_and_only_short_d1_slots_are_allowed(monkeypatch):
    monkeypatch.setattr(experiment.d1, "choose_policy", lambda *args, **kwargs: (None, evidence()))
    policy, report = experiment.risk_first_select(pd.DataFrame(), experiment.d1.Settings(),
                                                "switching_d1_risk_first", 20)
    assert policy == {"predictor": "hourly_d1", "max_length": 2, "tau": 0.9}
    assert not report.predictor.eq("hourly_pooled").any()
    assert report.max_length.eq(2).all()


def test_fixed_policy_cannot_switch_to_slot_model(monkeypatch):
    rows = evidence()
    rows.loc[rows.predictor == "hourly_d1", "accepted"] = False
    monkeypatch.setattr(experiment.d1, "choose_policy", lambda *args, **kwargs: (None, rows.copy()))
    policy, _ = experiment.risk_first_select(pd.DataFrame(), experiment.d1.Settings(),
                                            "fixed_d1_hourly_risk_first", 20)
    assert policy is None
    policy, _ = experiment.risk_first_select(pd.DataFrame(), experiment.d1.Settings(),
                                            "switching_d1_risk_first", 20)
    assert policy["predictor"] == "slot_d1"


def test_volume_uses_all_history_months_not_active_only(monkeypatch):
    rows = evidence()
    rows["announced_hours"] = 40
    monkeypatch.setattr(experiment.d1, "choose_policy", lambda *args, **kwargs: (None, rows.copy()))
    policy, report = experiment.risk_first_select(pd.DataFrame(), experiment.d1.Settings(),
                                                "fixed_d1_hourly_risk_first", 20)
    assert policy is None
    assert not report.volume_supported.any()


def test_zero_offer_month_fails_consistent_safety_and_volume():
    summary = pd.DataFrame([{"arm": "fixed", "mean_hours_per_month": 20.0,
                             "point_target_met": True, "months_above_target": 0}])
    monthly = pd.DataFrame({"arm": ["fixed", "fixed"], "announced_hours": [0, 40]})
    result = experiment.add_volume_metrics(summary, monthly, 20)
    assert result.mean_volume_benchmark_met.all()
    assert result.months_below_volume_benchmark.iloc[0] == 1
    assert not result.every_month_empirical_safety_and_volume.any()


def test_reused_predictor_data_must_not_be_test_or_other_horizon(tmp_path):
    columns = experiment.d1.slots.SLOT_KEY + ["date", "slot_end_utc", "start_hour", "quality_known", "y_slot",
                                            "near_zero_hours", "excess_sum", "prediction_month",
                                            *experiment.d1.PREDICTORS]
    row = dict.fromkeys(columns, 0)
    day = config.TEST_START
    row |= {"issue_ts": (day - pd.DateOffset(days=1) + pd.Timedelta(hours=config.ISSUE_HOUR)).isoformat(),
            "target_ts_utc": (day + pd.Timedelta(hours=9)).isoformat(),
            "slot_end_utc": (day + pd.Timedelta(hours=11)).isoformat(),
            "date": str(day.date()), "horizon_days": 1, "length": 2,
            "quality_known": True, "y_slot": True, "prediction_month": day.strftime("%Y-%m")}
    (tmp_path / "full").mkdir()
    pd.DataFrame([row]).to_csv(tmp_path / "full" / "predictions.csv", index=False)
    with pytest.raises(ValueError, match="validation-only"):
        experiment.read_predictions(tmp_path, {"prediction_months": [day.strftime("%Y-%m")]})


def test_fake_mode_cannot_read_source(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_MODE", "fake")
    with pytest.raises(SystemExit):
        experiment.main(["--source-dir", str(tmp_path / "absent"), "--run-dir", str(tmp_path / "unused")])
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("value", [-1, np.nan, np.inf])
def test_invalid_volume_benchmark_rejected_before_loading_source(tmp_path, value):
    with pytest.raises(ValueError):
        experiment.run(tmp_path / "absent", tmp_path / "unused", value)
    assert not (tmp_path / "unused").exists()