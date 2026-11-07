"""Synthetic regression checks for the isolated slot experiment, not real metrics."""

import importlib.util
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.models.base import feature_columns
from gridsense.models.chronological import PROFILES, default_score_months

# Console-entry pytest does not add the repository root to sys.path. Load the
# isolated script without changing packaging/configuration under an active queue.
_spec = importlib.util.spec_from_file_location(
    "gridsense_slot_experiment", Path(__file__).parents[1] / "experiments" / "slot_validation.py")
assert _spec is not None and _spec.loader is not None
experiment = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = experiment
_spec.loader.exec_module(experiment)


def hourly_rows(days=1, horizons=(1,), month=None):
    month = default_score_months()[0] if month is None else month
    first = pd.Timestamp(month, tz=config.LOCAL_TZ)
    parts = []
    for offset in range(days):
        day = first + pd.DateOffset(days=offset)
        target = pd.date_range(day + pd.Timedelta(hours=9), periods=9, freq="h")
        for horizon in horizons:
            price = np.where(np.arange(9) < 6, config.NEAR_ZERO_THRESHOLD_EUR - 1,
                             config.NEAR_ZERO_THRESHOLD_EUR + 30)
            parts.append(pd.DataFrame({
                "issue_ts": (day - pd.DateOffset(days=horizon)
                             + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_convert("UTC"),
                "target_ts_utc": target.tz_convert("UTC"), "horizon_days": horizon,
                "y_price": price, "y_near_zero": price <= config.NEAR_ZERO_THRESHOLD_EUR,
                "y_cheap": price <= config.CHEAP_THRESHOLD_EUR,
                "f_signal": np.arange(9, dtype=float), "f_weather": 10.0,
                "data_quality": "ok"}))
    return pd.concat(parts, ignore_index=True)


def test_candidate_keys_labels_and_known_feature_aggregates():
    slots = experiment.slot_table(hourly_rows(horizons=(1, 7)))
    assert len(slots) == 60  # 8+7+6+5+4 windows per horizon.
    assert not slots.duplicated(experiment.SLOT_KEY).any()
    assert slots.length.between(2, 6).all()
    assert (slots.start_hour + slots.length <= 18).all()
    first = slots[(slots.horizon_days == 1) & (slots.start_hour == 9) & (slots.length == 2)].iloc[0]
    assert first.y_slot and first.near_zero_hours == 2
    assert first.f_slot_signal_mean == 0.5
    assert first.f_slot_signal_min == 0 and first.f_slot_signal_max == 1
    later = slots[(slots.start_hour == 14) & (slots.length == 2)].iloc[0]
    assert not later.y_slot and later.near_zero_hours == 1


def test_label_changes_do_not_change_predictor_features_or_candidate_keys():
    rows = hourly_rows(days=2)
    before = experiment.slot_table(rows)
    changed = rows.copy()
    changed.y_price += 500
    changed["y_near_zero"] = changed["y_cheap"] = False
    after = experiment.slot_table(changed)
    columns = experiment.SLOT_KEY + feature_columns(before) + ["quality_known"]
    pd.testing.assert_frame_equal(before[columns], after[columns])
    assert not before.y_slot.equals(after.y_slot)
    assert not any(name in feature_columns(before) for name in
                   ("y_slot", "near_zero_hours", "excess_sum", "hourly_min"))


def test_missing_hour_is_never_bridged():
    rows = hourly_rows()
    rows = rows[rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.hour != 11]
    slots = experiment.slot_table(rows)
    assert not ((slots.start_hour <= 11) & (slots.start_hour + slots.length > 11)).any()


def test_missing_weather_remains_missing_and_quality_fails_closed():
    rows = hourly_rows()
    rows["f_weather"] = np.nan
    slots = experiment.slot_table(rows)
    assert slots.f_slot_weather_mean.isna().all()
    assert not slots.quality_known.any()
    assert experiment.plan_slots(slots, pd.Series(1.0, index=slots.index), 0) == []
    rows = hourly_rows().drop(columns="data_quality")
    assert not experiment.slot_table(rows).quality_known.any()


@pytest.mark.parametrize("problem", ["duplicate", "wrong_lead", "wrong_issue", "test", "infinite"])
def test_bad_hourly_inputs_are_rejected(problem):
    rows = hourly_rows()
    if problem == "duplicate":
        rows = pd.concat([rows, rows.iloc[:1]], ignore_index=True)
    elif problem == "wrong_lead":
        rows.horizon_days = 7
    elif problem == "wrong_issue":
        rows.issue_ts += pd.Timedelta(hours=1)
    elif problem == "test":
        shift = config.TEST_START - pd.Timestamp(default_score_months()[0], tz=config.LOCAL_TZ)
        rows.target_ts_utc += shift
        rows.issue_ts += shift
    else:
        rows.loc[0, "f_signal"] = np.inf
    with pytest.raises(ValueError):
        experiment.slot_table(rows)


def test_hourly_scores_require_exact_index_and_never_enter_slot_features():
    rows = hourly_rows()
    p = pd.Series(np.linspace(0.1, 0.9, len(rows)), index=rows.index)
    slots = experiment.slot_table(rows, p)
    assert "hourly_min" in slots and "hourly_min" not in feature_columns(slots)
    with pytest.raises(ValueError, match="align"):
        experiment.slot_table(rows, p.iloc[::-1])
    with pytest.raises(ValueError, match="probabilities"):
        experiment.slot_table(rows, p * np.nan)


def test_delivery_day_weights_do_not_inflate_overlapping_slots():
    slots = experiment.slot_table(hourly_rows(days=2, horizons=(1, 7)))
    weights = experiment.date_weights(slots)
    by_day = pd.Series(weights, index=slots.index).groupby(slots.date).sum()
    assert by_day.nunique() == 1


def test_replay_is_causal_no_future_month_ranking_and_no_label_ranking():
    slots = experiment.slot_table(hourly_rows(days=2))
    p = pd.Series(np.where(slots.date == slots.date.min(), 0.85, 0.99), index=slots.index)
    chosen = experiment.plan_slots(slots, p, 0.8)
    assert slots.loc[chosen].date.iloc[0] == slots.date.min()
    changed = slots.copy()
    changed.y_slot = ~changed.y_slot
    changed.excess_sum += 999
    assert experiment.plan_slots(changed, p, 0.8) == chosen
    shuffled = slots.sample(frac=1, random_state=config.RANDOM_SEED)
    assert experiment.plan_slots(shuffled, p.loc[shuffled.index], 0.8) == chosen


def test_replay_obeys_month_budget_duration_and_daily_overlap_caps():
    slots = experiment.slot_table(hourly_rows(days=28))
    chosen = experiment.plan_slots(slots, pd.Series(0.99, index=slots.index), 0.8)
    selected = slots.loc[chosen]
    assert selected.length.sum() <= experiment.MONTHLY_BUDGET_HOURS
    assert selected.groupby("date").size().le(experiment.MAX_SLOTS_PER_DAY).all()
    for _, group in selected.groupby("date"):
        ordered = group.sort_values("start_hour")
        assert all(first.start_hour + first.length <= second.start_hour for first, second in
                   zip(ordered.iloc[:-1].itertuples(), ordered.iloc[1:].itertuples()))


def test_no_offers_are_not_reported_as_perfect_safety_or_capture():
    slots = experiment.slot_table(hourly_rows())
    result = experiment.outcomes(slots, [])
    assert result["slots"] == result["announced_hours"] == 0
    assert result["cancellation_rate"] is result["slot_hit_rate"] is None
    assert result["captured_opportunity_days"] == 0 and result["opportunity_days"] == 1


def test_mixed_horizon_replay_is_rejected():
    slots = experiment.slot_table(hourly_rows(horizons=(1, 7)))
    with pytest.raises(ValueError, match="separately"):
        experiment.plan_slots(slots, pd.Series(0.99, index=slots.index), 0.8)


def test_wilson_uses_days_not_overlapping_slot_count():
    assert experiment.wilson_lower(15, 15, 0.9) >= 0.9
    assert experiment.wilson_lower(2, 2, 0.9) < 0.9
    assert experiment.wilson_lower(0, 0, 0.9) == 0


def test_conservative_gate_abstains_without_enough_evidence():
    slots = experiment.slot_table(hourly_rows(days=2))
    slots.y_slot = True
    p = pd.Series(0.99, index=slots.index)
    settings = experiment.PolicySettings()
    tau, reports = experiment.select_threshold(slots, p, True, settings)
    assert tau is None and not any(row["accepted"] for row in reports)
    ordinary, _ = experiment.select_threshold(slots, p, False, settings)
    assert ordinary is not None


def test_conservative_gate_can_accept_supported_stable_predictions():
    slots = experiment.slot_table(hourly_rows(days=28))
    slots.y_slot = True
    p = pd.Series(np.where(slots.length == 2, 0.99, 0.1), index=slots.index)
    settings = replace(experiment.PolicySettings(), min_support_days=15)
    tau, reports = experiment.select_threshold(slots, p, True, settings)
    assert tau is not None and tau >= settings.min_probability
    assert any(row["accepted"] for row in reports)


def test_missing_quality_never_passes_even_at_zero_threshold():
    slots = experiment.slot_table(hourly_rows(days=28))
    slots.quality_known = False
    p = pd.Series(1.0, index=slots.index)
    for conservative in (False, True):
        tau, _ = experiment.select_threshold(slots, p, conservative, experiment.PolicySettings())
        assert tau is None


def test_earlier_calibration_mapping_does_not_use_later_labels():
    slots = experiment.slot_table(hourly_rows(days=2))
    p = np.where(slots.y_slot, 0.8, 0.2)
    mapping = experiment.fit_mapping(p, slots)
    before = experiment.mapped_probability(mapping, p)
    later = slots.copy()
    later.y_slot = ~later.y_slot
    np.testing.assert_array_equal(experiment.mapped_probability(mapping, p), before)
    with pytest.raises(ValueError, match="both classes"):
        experiment.fit_mapping(p, slots.assign(y_slot=True))


def test_profile_definitions_are_not_mutated():
    before = deepcopy(PROFILES)
    for profile in PROFILES:
        options = dict(PROFILES[profile])
        options.pop("half_life_days")
        steps = options.pop("step_half_lives")
        assert experiment.NEAR_ZERO in steps
        options["n_jobs"] = 1
    assert PROFILES == before


def test_replay_does_not_consume_budget_using_later_high_scores(monkeypatch):
    monkeypatch.setattr(experiment, "MONTHLY_BUDGET_HOURS", 2)
    slots = experiment.slot_table(hourly_rows(days=2))
    p = pd.Series(np.where(slots.date == slots.date.min(), 0.81, 0.99), index=slots.index)
    chosen = experiment.plan_slots(slots, p, 0.8)
    assert len(chosen) == 1 and slots.loc[chosen[0], "date"] == slots.date.min()


def test_known_issue_time_features_are_unchanged_by_other_days():
    rows = hourly_rows(days=2)
    before = experiment.slot_table(rows)
    first_day = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.date.min()
    later = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.date != first_day
    rows.loc[later, "f_signal"] = 9999
    after = experiment.slot_table(rows)
    pd.testing.assert_frame_equal(before[before.date == first_day], after[after.date == first_day])


def test_real_mode_guard_rejects_fake_without_loading_data(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_MODE", "fake")
    with pytest.raises(SystemExit):
        experiment.main(["--run-dir", str(tmp_path / "unused"), "--execute"])
    assert not (tmp_path / "unused").exists()