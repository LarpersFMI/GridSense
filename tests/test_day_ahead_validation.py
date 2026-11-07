"""Synthetic D+1 protocol tests; never count these fixtures as market results."""

import importlib.util
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.models.chronological import default_score_months

# Keep standalone experiments outside installed/protected production packaging.
_root = Path(__file__).parents[1] / "experiments"
if "experiments" not in sys.modules:
    _package_spec = importlib.util.spec_from_file_location(
        "experiments", _root / "__init__.py", submodule_search_locations=[str(_root)])
    assert _package_spec is not None and _package_spec.loader is not None
    _package = importlib.util.module_from_spec(_package_spec)
    sys.modules["experiments"] = _package
    _package_spec.loader.exec_module(_package)
_spec = importlib.util.spec_from_file_location("experiments.day_ahead_validation",
                                              _root / "day_ahead_validation.py")
assert _spec is not None and _spec.loader is not None
experiment = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = experiment
_spec.loader.exec_module(experiment)


@pytest.fixture
def development_table():
    days = pd.date_range(config.TRAIN_START, config.VAL_END.normalize(), freq="D")
    wall_days = days.tz_localize(None)
    parts = []
    for horizon in config.HORIZONS_DAYS:
        for hour in (9, 10):
            prices = np.where(np.arange(len(days)) % 3 == 0,
                              config.NEAR_ZERO_THRESHOLD_EUR - 1,
                              config.NEAR_ZERO_THRESHOLD_EUR + 50)
            parts.append(pd.DataFrame({
                "issue_ts": (wall_days - pd.DateOffset(days=horizon)
                             + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(
                                 config.LOCAL_TZ).tz_convert("UTC"),
                "target_ts_utc": (wall_days + pd.Timedelta(hours=hour)).tz_localize(
                    config.LOCAL_TZ).tz_convert("UTC"),
                "horizon_days": horizon, "y_price": prices,
                "y_near_zero": prices <= config.NEAR_ZERO_THRESHOLD_EUR,
                "f_signal": np.arange(len(days)) % 3, "data_quality": "ok"}))
    return pd.concat(parts, ignore_index=True)


def test_prediction_blocks_are_forward_only_and_purged(development_table):
    stages, metadata = experiment.prediction_stages(development_table, default_score_months()[0])
    names = list(stages)
    for before, after in itertools.pairwise(names):
        assert stages[before].target_ts_utc.max() < stages[after].issue_ts.min()
        assert not set(stages[before].target_ts_utc).intersection(stages[after].target_ts_utc)
        assert metadata["purged_rows"][before] > 0
    for part in stages.values():
        assert part.groupby("target_ts_utc").horizon_days.nunique().eq(7).all()


def test_stage_features_are_dropped_using_fit_only(development_table):
    month = default_score_months()[0]
    stages, _ = experiment.prediction_stages(development_table, month)
    table = development_table.copy()
    table["f_later_only"] = 1.0
    table.loc[stages["fit"].index, "f_later_only"] = np.nan
    parts, metadata = experiment.prediction_stages(table, month)
    assert "f_later_only" in metadata["dropped_features"]
    assert all("f_later_only" not in part for part in parts.values())


@pytest.mark.parametrize("bad", ["test", "refit", "duplicate", "label", "issue", "horizon"])
def test_reject_invalid_input(development_table, bad):
    table = development_table.copy()
    if bad in ("test", "refit"):
        table.loc[0, "target_ts_utc"] = (config.TEST_START if bad == "test"
                                        else config.VAL_END + pd.Timedelta(days=1)).tz_convert("UTC")
    elif bad == "duplicate":
        table = pd.concat([table, table.iloc[:1]], ignore_index=True)
    elif bad == "label":
        table.loc[0, "y_near_zero"] = not table.loc[0, "y_near_zero"]
    elif bad == "issue":
        table.loc[0, "issue_ts"] += pd.Timedelta(hours=1)
    else:
        table.loc[0, "horizon_days"] = 99
    with pytest.raises(ValueError):
        experiment.validate_table(table)


def test_score_labels_do_not_change_prior_model_stages(development_table):
    month = default_score_months()[0]
    before, _ = experiment.prediction_stages(development_table, month)
    table = development_table.copy()
    index = before["prediction"].index
    table.loc[index, "y_price"] = config.NEAR_ZERO_THRESHOLD_EUR + 999
    table.loc[index, "y_near_zero"] = False
    after, _ = experiment.prediction_stages(table, month)
    for name in ("fit", "early_stop", "calibration"):
        pd.testing.assert_frame_equal(before[name], after[name])


def test_policy_history_excludes_score_and_unavailable_end_hours(development_table):
    month = pd.Period(default_score_months()[0], freq="M")
    predictions = {}
    for offset in (-3, -2, -1, 0):
        name = str(month + offset)
        _, metadata = experiment.prediction_stages(development_table, name)
        rows = development_table[development_table.horizon_days == 1]
        local_month = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.strftime("%Y-%m")
        candidates = experiment.slots.slot_table(rows[local_month == name])
        predictions[name] = candidates
        assert metadata["prediction_month"] == name
    history = experiment.history_before(predictions, str(month), experiment.Settings())
    cutoff = predictions[str(month)].issue_ts.min().tz_convert(config.LOCAL_TZ).normalize()
    assert (history.slot_end_utc <= cutoff).all()
    assert history.target_ts_utc.max() < predictions[str(month)].target_ts_utc.min()
    assert not history.empty


def make_policy_history(success=True):
    dates = pd.date_range(config.VAL_START, periods=90, freq="D")
    wall_dates = dates.tz_localize(None)
    target = (wall_dates + pd.Timedelta(hours=9)).tz_localize(config.LOCAL_TZ).tz_convert("UTC")
    frame = pd.DataFrame({"issue_ts": (wall_dates - pd.DateOffset(days=1)
                                      + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(
                                          config.LOCAL_TZ).tz_convert("UTC"),
                          "target_ts_utc": target, "slot_end_utc": target + pd.Timedelta(hours=2),
                          "date": dates.date, "horizon_days": 1, "start_hour": 9, "length": 2,
                          "quality_known": True, "y_slot": success, "near_zero_hours": 2,
                          "excess_sum": 0.0})
    for predictor in experiment.PREDICTORS:
        frame[predictor] = 0.95
    return frame


def test_supported_three_month_policy_can_pass_without_long_slots():
    policy, evidence = experiment.choose_policy(make_policy_history(), experiment.Settings())
    assert policy is not None and policy["max_length"] == 2
    accepted = evidence[evidence.accepted]
    assert accepted.active_days.ge(15).all()
    assert accepted.active_months.ge(2).all()
    assert accepted.day_hit_lower_bound.ge(0.9).all()


def test_poor_month_cannot_be_hidden_by_pooled_good_months():
    history = make_policy_history()
    last = history.date >= pd.Timestamp(config.VAL_START + pd.DateOffset(months=2)).date()
    history.loc[last, "y_slot"] = False
    policy, _ = experiment.choose_policy(history, experiment.Settings())
    assert policy is None


def test_quality_and_support_gates_do_not_weaken_to_make_offers():
    history = make_policy_history().iloc[:9]
    policy, _ = experiment.choose_policy(history, experiment.Settings())
    assert policy is None
    history = make_policy_history().assign(quality_known=False)
    policy, _ = experiment.choose_policy(history, experiment.Settings())
    assert policy is None


def test_apply_policy_is_label_independent_and_causal():
    candidates = make_policy_history().iloc[:3]
    policy = {"predictor": "hourly_d1", "max_length": 2, "tau": 0.9}
    before = experiment.apply_policy(candidates, policy)
    changed = candidates.assign(y_slot=False, excess_sum=999)
    assert experiment.apply_policy(changed, policy) == before
    assert experiment.apply_policy(changed, None) == []


def test_single_class_calibration_does_not_borrow_future_labels():
    calibration = make_policy_history(False)
    raw = np.full(len(calibration), 0.99)
    predicted, reason = experiment.calibrate_probability(raw, calibration, np.array([0.1, 0.99]))
    assert predicted[0] == predicted[1] and predicted.max() < 0.8
    assert "single-class" in reason
    mapping, reason = experiment.calibrate_probability(raw, calibration.assign(quality_known=False), raw)
    assert not mapping.any()


def test_zero_offers_do_not_satisfy_point_target():
    report = experiment.slots.outcomes(make_policy_history(), [])
    summary = experiment.summary_report(pd.DataFrame([report | {
        "arm": "d1_conservative", "abstained": True}]))
    assert not summary.point_target_met.any()
    assert summary.cancellation_rate.isna().all()
    assert not summary.deployment_approved.any()


def test_main_rejects_fake_without_creating_run(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_MODE", "fake")
    with pytest.raises(SystemExit):
        experiment.main(["--execute", "--run-dir", str(tmp_path / "unused")])
    assert not (tmp_path / "unused").exists()


def test_real_lightgbm_early_stop_api_accepts_stage_matrices(development_table):
    # The installed LightGBM eval_X API treats list-of-frames as a data matrix,
    # while tuple-of-frames means validation sets. Exercise the real fit path.
    fit = development_table[development_table.horizon_days == 1].iloc[:120]
    stop = development_table[development_table.horizon_days == 1].iloc[120:180]
    model, features, _ = experiment.fit_model(
        fit, stop, "y_near_zero", {"n_estimators": 2, "verbose": -1, "min_child_samples": 2},
        730.0, experiment.Settings(), smoke=True)
    probability = experiment.positive_probability(model, stop[features])
    assert probability.shape == (len(stop),) and np.isfinite(probability).all()


def test_progress_counts_finished_work_only_and_writes_json(tmp_path, capsys):
    tracker = experiment.RunProgress(tmp_path, total=3, smoke=False)
    tracker.update("starting")
    value = experiment.json.loads((tmp_path / "progress.json").read_text())
    assert value["percent"] == 0 and value["completed_steps"] == 0
    tracker.update("one model complete", finished=True)
    tracker.update("second model starting")
    value = experiment.json.loads((tmp_path / "progress.json").read_text())
    assert value["percent"] == 33.3 and value["completed_steps"] == 1
    tracker.update("second model complete", finished=True)
    tracker.finish()
    value = experiment.json.loads((tmp_path / "progress.json").read_text())
    assert value["percent"] == 100 and value["state"] == "completed"
    assert not value["test_evaluated"]
    assert "[D+1 progress 100.0%]" in capsys.readouterr().out


def test_progress_does_not_report_completion_early(tmp_path):
    tracker = experiment.RunProgress(tmp_path, total=3, smoke=True)
    with pytest.raises(ValueError, match="unfinished work"):
        tracker.finish()
    value = experiment.json.loads((tmp_path / "progress.json").read_text())
    assert value["percent"] < 100 and value["state"] == "running"


def test_progress_rejects_extra_completed_work(tmp_path):
    tracker = experiment.RunProgress(tmp_path, total=1, smoke=True)
    tracker.finish()
    with pytest.raises(ValueError, match="exceeds"):
        tracker.update("unexpected extra work", finished=True)