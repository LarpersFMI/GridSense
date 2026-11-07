from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.models import chronological
from gridsense.models.base import PRICE_COLUMNS
from gridsense.models.baselines import NAIVE_COLUMN, PERSISTENCE_COLUMN
from gridsense.schemas import TRAINING_TABLE
from gridsense.splits import assign_split


def _first_score_month():
    return pd.Period(config.VAL_START.date(), freq="M") + 3


@pytest.fixture
def development_table():
    """Synthetic: one delivery hour per local day, repeated at every configured horizon."""
    days = pd.date_range(config.TRAIN_START.normalize(), config.VAL_END.normalize(), freq="D")
    price = np.where(
        np.arange(len(days)) % 3 == 0,
        config.CHEAP_THRESHOLD_EUR - 1,
        np.where(np.arange(len(days)) % 3 == 1,
                 (config.CHEAP_THRESHOLD_EUR + config.NEAR_ZERO_THRESHOLD_EUR) / 2,
                 config.NEAR_ZERO_THRESHOLD_EUR + 30),
    )
    parts = []
    for horizon in config.HORIZONS_DAYS:
        parts.append(pd.DataFrame({
            "issue_ts": (days - pd.DateOffset(days=horizon)
                         + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_convert("UTC"),
            "target_ts_utc": (days + pd.Timedelta(hours=6)).tz_convert("UTC"),
            "horizon_days": horizon,
            "y_price": price,
            "y_near_zero": price <= config.NEAR_ZERO_THRESHOLD_EUR,
            "y_cheap": price <= config.CHEAP_THRESHOLD_EUR,
            "f_signal": np.arange(len(days)) % 5,
            "f_horizon_days": horizon,
            NAIVE_COLUMN: price,
            PERSISTENCE_COLUMN: price,
        }))
    table = pd.concat(parts, ignore_index=True)
    assert set(TRAINING_TABLE) <= set(table)
    return table


def _slot_rows(days=1, month=None):
    month = _first_score_month() if month is None else month
    start = month.start_time.tz_localize(config.LOCAL_TZ)
    target = pd.date_range(start, start + pd.DateOffset(days=days), freq="h", inclusive="left")
    price = config.NEAR_ZERO_THRESHOLD_EUR - 1
    return pd.DataFrame({
        "target_ts_utc": target.tz_convert("UTC"),
        "horizon_days": min(config.HORIZONS_DAYS),
        "y_price": price,
        "y_near_zero": True,
        "y_cheap": price <= config.CHEAP_THRESHOLD_EUR,
        NAIVE_COLUMN: price,
        PERSISTENCE_COLUMN: price,
        "f_signal": 0.9,
    })


def test_score_months_come_from_config():
    months = pd.period_range(config.VAL_START.date(), config.VAL_END.date(), freq="M")
    assert chronological.default_score_months() == [str(month) for month in months[3:]]
    assert chronological.default_score_months()[0] == str(_first_score_month())


def test_month_fold_groups_targets_and_purges_at_next_issue_local_day(development_table):
    month = _first_score_month()
    stages, metadata = chronological.month_fold(development_table, str(month))
    target_months = (development_table.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
                     .dt.tz_localize(None).dt.to_period("M"))
    original = {"fit": development_table[target_months < month - 3]}
    original.update({name: development_table[target_months == month + offset]
                     for name, offset in zip(chronological.STAGES[1:], (-3, -2, -1, 0),
                                             strict=True)})
    seen = set()
    for name in chronological.STAGES:
        part = stages[name]
        targets = set(part.target_ts_utc)
        assert not seen.intersection(targets)
        seen.update(targets)
        groups = part.groupby("target_ts_utc").horizon_days
        assert groups.size().eq(len(config.HORIZONS_DAYS)).all()
        assert groups.apply(lambda horizons: set(horizons) == set(config.HORIZONS_DAYS)).all()
        assert metadata["stages"][name]["unique_targets"] == len(targets)

    for before, after in zip(chronological.STAGES[:-1], chronological.STAGES[1:], strict=True):
        earliest_issue = original[after].issue_ts.min().tz_convert(config.LOCAL_TZ)
        cutoff = earliest_issue.normalize()
        local_targets = original[before].target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
        expected = original[before][local_targets < cutoff]
        pd.testing.assert_frame_equal(stages[before], expected)
        assert stages[before].target_ts_utc.max() < cutoff
        assert stages[before].target_ts_utc.max() < stages[after].issue_ts.min()
        # Delivery labels need no extra seven-day delay; retain the day before cutoff.
        last_day = stages[before].target_ts_utc.max().tz_convert(config.LOCAL_TZ).normalize()
        assert last_day == cutoff - pd.DateOffset(days=1)
        # Even a 06:00 delivery on the 10:00 issue day is conservatively excluded.
        assert ((local_targets >= cutoff) & (local_targets < earliest_issue)).any()
        assert metadata["purged_rows"][before] == len(original[before]) - len(expected)
    pd.testing.assert_frame_equal(stages["score"], original["score"])


@pytest.mark.parametrize("invalid_split", ["test", "unassigned"])
def test_month_fold_rejects_non_development_targets(development_table, invalid_split):
    extra = development_table.iloc[[0]].copy()
    day = (config.TEST_START if invalid_split == "test"
           else config.VAL_END.normalize() + pd.DateOffset(days=1))
    extra["target_ts_utc"] = (day + pd.Timedelta(hours=6)).tz_convert("UTC")
    extra["issue_ts"] = (day - pd.DateOffset(days=1)
                         + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_convert("UTC")
    table = pd.concat([development_table, extra], ignore_index=True)
    with pytest.raises(ValueError, match="labelled train/validation rows only"):
        chronological.month_fold(table, str(_first_score_month()))


@pytest.mark.parametrize("label", ["y_price", "y_near_zero", "y_cheap"])
def test_month_fold_rejects_conflicting_repeated_target_labels(development_table, label):
    table = development_table.copy()
    table.loc[0, label] = table.loc[0, label] + 1 if label == "y_price" else not table.loc[0, label]
    with pytest.raises(ValueError, match="Repeated target labels must agree"):
        chronological.month_fold(table, str(_first_score_month()))


@pytest.mark.parametrize("invalid_month", ["too_early", "after_validation", "malformed"])
def test_month_fold_rejects_invalid_score_month(development_table, invalid_month):
    choices = {
        "too_early": str(_first_score_month() - 1),
        "after_validation": str(pd.Period(config.VAL_END.date(), freq="M") + 1),
        "malformed": "not-a-month",
    }
    with pytest.raises(ValueError):
        chronological.month_fold(development_table, choices[invalid_month])


def test_month_fold_drops_empty_features_using_fit_only(development_table):
    stages, _ = chronological.month_fold(development_table, str(_first_score_month()))
    table = development_table.copy()
    table["f_future_only"] = 1.0
    table.loc[stages["fit"].index, "f_future_only"] = np.nan
    table["f_fit_only"] = np.nan
    table.loc[stages["fit"].index, "f_fit_only"] = 1.0
    result, metadata = chronological.month_fold(table, str(_first_score_month()))
    assert metadata["dropped_features"] == ["f_future_only"]
    for name, part in result.items():
        assert "f_future_only" not in part
        assert "f_fit_only" in part
        assert part.f_fit_only.notna().all() if name == "fit" else part.f_fit_only.isna().all()


def test_score_target_label_and_feature_changes_leave_earlier_blocks_identical(development_table):
    month = str(_first_score_month())
    before, before_meta = chronological.month_fold(development_table, month)
    table = development_table.copy()
    held = before["score"].index
    table.loc[held, "target_ts_utc"] += pd.Timedelta(hours=1)
    table.loc[held, "y_price"] += 100
    table.loc[held, ["y_near_zero", "y_cheap"]] = False
    table.loc[held, "f_signal"] = -100
    after, after_meta = chronological.month_fold(table, month)
    for name in chronological.STAGES[:-1]:
        pd.testing.assert_frame_equal(before[name], after[name])
        assert before_meta["stages"][name] == after_meta["stages"][name]
    assert before_meta["purged_rows"] == after_meta["purged_rows"]
    assert before_meta["dropped_features"] == after_meta["dropped_features"]
    assert not before["score"].equals(after["score"])


@pytest.mark.parametrize(("hours", "slots", "announced"), [
    ([9], 0, 0),
    ([9, 10], 1, 2),
    (list(range(9, 15)), 1, 6),
    (list(range(9, 18)), 2, 9),
    ([9, 10, 12, 13, 15, 16], 2, 4),
    ([8, 9, 17, 18], 0, 0),
    (list(range(24)), 2, 9),
])
def test_threshold_slot_duration_window_and_daily_cap(hours, slots, announced):
    rows = _slot_rows()
    local_hour = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.hour
    probability = pd.Series(np.where(local_hour.isin(hours), 0.9, 0.0), index=rows.index)
    rows.loc[~local_hour.isin(chronological.SLOT_HOURS), "y_price"] = (
        config.NEAR_ZERO_THRESHOLD_EUR + 100
    )
    result = chronological.threshold_slots(rows, probability, tau=0.8)
    assert result["slots"] == slots
    assert result["announced_hours"] == announced
    if slots:
        assert result["slot_hit_rate"] == 1.0


def test_threshold_slots_obeys_monthly_budget_without_forcing_a_quota():
    rows = _slot_rows(days=28)
    probability = pd.Series(0.9, index=rows.index)
    result = chronological.threshold_slots(rows, probability, tau=0.8)
    assert result["announced_hours"] == chronological.MONTHLY_BUDGET_HOURS
    abstain = chronological.threshold_slots(rows, probability, tau=0.95)
    assert abstain["slots"] == abstain["announced_hours"] == 0
    assert abstain["slot_hit_rate"] is abstain["cancellation_rate"] is None


def test_threshold_slots_resets_budget_for_each_target_month():
    rows = pd.concat([_slot_rows(days=28, month=_first_score_month() + offset)
                      for offset in (0, 1)], ignore_index=True)
    result = chronological.threshold_slots(rows, pd.Series(0.9, index=rows.index), tau=0.8)
    assert result["announced_hours"] == 2 * chronological.MONTHLY_BUDGET_HOURS


def test_threshold_requires_every_hour_not_just_the_block_mean():
    rows = _slot_rows()
    hour = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.hour
    probability = pd.Series(0.0, index=rows.index)
    probability.loc[hour.eq(9)] = 1.0
    probability.loc[hour.eq(10)] = 0.6  # Mean 0.8 passes, but the second hour fails.
    result = chronological.threshold_slots(rows, probability, tau=0.8)
    assert result["slots"] == result["announced_hours"] == 0


def test_threshold_ties_are_deterministic_and_do_not_rank_by_realised_labels(monkeypatch):
    monkeypatch.setattr(chronological, "MONTHLY_BUDGET_HOURS", 6)
    rows = _slot_rows(days=2)
    local = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
    preferred = local.dt.day.eq(1) & local.dt.hour.between(9, 14)
    rows.loc[~preferred, "y_price"] = config.NEAR_ZERO_THRESHOLD_EUR + 100
    probability = pd.Series(0.9, index=rows.index)
    first = chronological.threshold_slots(rows, probability, tau=0.8)
    shuffled = rows.sample(frac=1, random_state=config.RANDOM_SEED)
    assert chronological.threshold_slots(shuffled, probability, tau=0.8) == first
    assert first["slots"] == 1 and first["announced_hours"] == 6
    assert first["slot_hit_rate"] == 1.0
    rows.loc[preferred, "y_price"] = config.NEAR_ZERO_THRESHOLD_EUR + 100
    rows.loc[local.dt.day.eq(2), "y_price"] = config.NEAR_ZERO_THRESHOLD_EUR - 1
    changed = chronological.threshold_slots(rows, probability, tau=0.8)
    assert changed["slots"] == 1 and changed["announced_hours"] == 6
    assert changed["slot_hit_rate"] == 0.0


def test_select_policy_abstains_when_no_candidate_meets_cancellation_limit():
    rows = _slot_rows(days=3)
    rows["y_price"] = config.NEAR_ZERO_THRESHOLD_EUR + 100
    rows = pd.concat([rows.assign(horizon_days=horizon)
                      for horizon in (min(config.HORIZONS_DAYS), max(config.HORIZONS_DAYS))],
                     ignore_index=True)
    scores = {"classifier": pd.Series(0.9, index=rows.index)}
    policies, candidates = chronological.select_policy(rows, scores)
    assert policies == {horizon: None for horizon in rows.horizon_days.unique()}
    announced = [candidate for candidate in candidates if candidate["slots"]]
    assert announced
    assert all(candidate["cancellation_rate"] > chronological.MAX_CANCELLATION
               for candidate in announced)


class _StubModel:
    """Feature-independent predictions: no LightGBM/LEAR fitting or model weights."""

    name = "stub"
    quantiles = config.QUANTILES

    def __init__(self, **kwargs):
        self.params = kwargs.get("params", {})
        self.calibrators = {}

    def fit(self, *args):
        return self

    def predict(self, rows, **kwargs):
        pred = pd.DataFrame(config.NEAR_ZERO_THRESHOLD_EUR - 1,
                            index=rows.index, columns=list(PRICE_COLUMNS))
        return pred.assign(p_near_zero=0.9, p_cheap=0.2)

    def predict_quantiles(self, rows):
        pred = self.predict(rows)
        return dict(zip(config.QUANTILES, (pred[column] for column in PRICE_COLUMNS), strict=True))

    def best_iterations(self):
        return {}

    def step_probabilities(self, rows, **kwargs):
        return {step: np.full(len(rows), 0.9) for step in chronological.STEPS}

    def metadata(self):
        return {"structure": "stub-chain"}


def test_fit_fold_selects_on_selection_not_score_labels(development_table, monkeypatch):
    stages, _ = chronological.month_fold(development_table, str(_first_score_month()))
    assert assign_split(stages["score"].target_ts_utc).eq("val").all()
    stages["selection"] = _slot_rows(days=3, month=_first_score_month() - 1)
    stages["score"] = _slot_rows(days=3)
    for name in ("PriceForecaster", "LowPriceClassifier", "LEAR"):
        monkeypatch.setattr(chronological, name, _StubModel)
    monkeypatch.setattr(chronological, "conformal_offsets", lambda *args, **kwargs: {})
    monkeypatch.setattr(chronological, "fit_calibrator", lambda *args: SimpleNamespace(
        predict=lambda probability: np.full(len(probability), 0.9)))
    for name in ("price_scores", "classification_scores", "budget_metrics"):
        monkeypatch.setattr(chronological, name, lambda *args: pd.DataFrame())

    before = chronological.fit_fold(stages, smoke=True)
    changed = {name: part.copy() for name, part in stages.items()}
    changed["score"]["y_price"] = config.NEAR_ZERO_THRESHOLD_EUR + 100
    changed["score"][["y_near_zero", "y_cheap"]] = False
    after = chronological.fit_fold(changed, smoke=True)
    assert before["metadata"]["policies"] == after["metadata"]["policies"]
    assert all(policy is not None for policy in before["metadata"]["policies"].values())
    pd.testing.assert_frame_equal(before["selection"], after["selection"])
    for column in ("tau", "ranker", "slots", "announced_hours"):
        pd.testing.assert_series_equal(before["policy_score"][column], after["policy_score"][column])
    assert before["policy_score"].cancellation_rate.eq(0).all()
    assert after["policy_score"].cancellation_rate.eq(1).all()


def test_forward_calibration_filters_conditional_step_and_ignores_score_labels(monkeypatch):
    from gridsense.models.classify import CHEAP_GIVEN_NEAR_ZERO, NEAR_ZERO

    calib = pd.DataFrame({"y_near_zero": [True, True, False], "y_cheap": [True, False, False]})
    model = _StubModel()
    calls = []

    def calibrator(probability, labels, method):
        calls.append((probability.copy(), labels.copy()))
        return SimpleNamespace(predict=lambda p: p)

    monkeypatch.setattr(chronological, "fit_calibrator", calibrator)
    chronological.calibrate_chain(model, calib)
    assert set(model.calibrators) == {NEAR_ZERO, CHEAP_GIVEN_NEAR_ZERO}
    assert [len(values) for values, _ in calls] == [3, 2]
    np.testing.assert_array_equal(calls[1][1], [1, 0])
    changed = calib.copy()
    changed.loc[~changed.y_near_zero, "y_cheap"] = True
    calls.clear()
    chronological.calibrate_chain(model, changed)
    np.testing.assert_array_equal(calls[1][1], [1, 0])