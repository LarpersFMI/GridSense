import numpy as np
import pandas as pd
import pytest

from gridsense import config, io
from gridsense.models import evaluate, train
from gridsense.models.metrics import block_slots, slot_hit_rate, slot_outcomes

DAY = pd.Timestamp("2025-07-07", tz=config.LOCAL_TZ)


def _local(hour: int) -> pd.Timestamp:
    return (DAY + pd.Timedelta(hours=hour)).tz_convert("UTC")


def _predictions(p_by_hour: dict[int, float], horizon: int = 1) -> pd.DataFrame:
    """One forecast (issue, horizon) for DAY, local hours 06-21; p = 0 unless given."""
    hours = range(6, 22)
    return pd.DataFrame(
        {
            "issue_ts": _local(-14 - 24 * (horizon - 1)),
            "horizon_days": horizon,
            "target_ts_utc": [_local(h) for h in hours],
            "p": [p_by_hour.get(h, 0.0) for h in hours],
        }
    )


def test_block_slots_finds_runs_inside_the_window():
    # 08:00 is outside 09-18; 10-12 is a 3 h run; 15:00 alone is too short.
    preds = _predictions({8: 0.9, 9: 0.2, 10: 0.9, 11: 0.8, 12: 0.7, 15: 0.9})
    slots = block_slots(preds, "p", tau=0.5)

    assert len(slots) == 1
    slot = slots.iloc[0]
    assert slot["slot_start"] == _local(10) and slot["slot_end"] == _local(13)
    assert slot["hours"] == 3
    assert slot["p_mean"] == pytest.approx(0.8)


def test_block_slots_cuts_long_runs_and_keeps_forecasts_apart():
    preds = _predictions({h: 0.9 for h in range(9, 18)})  # 9 h run: 6 h + 3 h
    both = pd.concat([preds, _predictions({h: 0.9 for h in range(9, 18)}, horizon=2)])
    slots = block_slots(both, "p", tau=0.5)

    assert sorted(slots["hours"]) == [3, 3, 6, 6]
    assert set(slots["horizon_days"]) == {1, 2}
    assert (slots["slot_end"] <= _local(18)).all()


def test_block_slots_empty_when_nothing_clears_tau():
    slots = block_slots(_predictions({}), "p", tau=0.5)
    assert slots.empty
    assert np.isnan(slot_hit_rate(slots, pd.DataFrame(columns=["ts_utc", "price_mean"])))


def test_slot_outcomes_and_hit_rate():
    prices = pd.DataFrame({"ts_utc": [_local(h) for h in range(9, 18)]})
    prices["price_mean"] = [-5.0, -1.0, 0.0, 30.0, -2.0, -3.0, -4.0, -5.0, -6.0]
    slots = pd.DataFrame(
        {
            "slot_start": [_local(9), _local(11), _local(14), _local(16)],
            "slot_end": [_local(12), _local(13), _local(16), _local(19)],
        }
    )
    out = slot_outcomes(slots, prices, threshold=0.0)

    assert out["hours"].tolist() == [3, 2, 2, 3]
    assert out["cheap_hours"].tolist() == [3, 1, 2, 2]
    # Slot 4 runs into 18:00, which has no price: outcome unknown, left out of the rate.
    assert out["hit"].iloc[:3].tolist() == [1.0, 0.0, 1.0] and np.isnan(out["hit"].iloc[3])
    assert slot_hit_rate(slots, prices, threshold=0.0) == pytest.approx(2 / 3)


def test_evaluate_writes_slot_sweep(tiny_training_table, tmp_dirs):
    io.write(tiny_training_table, "training_table")
    train.main(["--task", "classify"])
    evaluate.main(["--task", "classify"])

    sweep = pd.read_csv(config.REPORTS_DIR / "eval" / "classify_slots_val.csv")
    assert set(sweep["tau"]) == set(evaluate.TAUS)
    assert {"slots", "slot_hours", "hit_rate", "cheap_hours_captured"} <= set(sweep.columns)
    assert sweep["hit_rate"].dropna().between(0, 1).all()
    assert sweep["cheap_hours_captured"].dropna().between(0, 1).all()
