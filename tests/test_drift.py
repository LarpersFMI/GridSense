import numpy as np
import pandas as pd
import pytest

from gridsense import config, io
from gridsense.models import drift, train
from gridsense.models.drift import model_drift_rows
from gridsense.models.metrics import DRIFT_Z, calibration_drift, slot_drift, weekly_drift
from gridsense.schemas import MODEL_DRIFT


def _hours(start: str, weeks: int) -> pd.Series:
    """Hourly UTC timestamps covering whole local weeks from a local Monday (no DST change)."""
    local = pd.date_range(start, periods=weeks * 7 * 24, freq="h", tz=config.LOCAL_TZ)
    return pd.Series(local.tz_convert("UTC"))


def test_calibrated_model_is_not_flagged_and_pessimistic_one_is():
    rng = np.random.default_rng(0)
    ts = _hours("2025-06-02", 4)
    p = pd.Series(rng.uniform(0, 0.4, len(ts)))
    y = pd.Series(rng.uniform(0, 1, len(ts)) < p)

    honest = calibration_drift(ts, p, y)
    assert abs(honest["z_calibration"]) < DRIFT_Z
    assert honest["oe_ratio"] == pytest.approx(1, abs=0.1)

    low = calibration_drift(ts, p / 3, y)  # model predicts 3x too few low-price hours
    assert low["z_calibration"] > DRIFT_Z
    assert low["oe_ratio"] > 2


def test_repeated_horizons_do_not_inflate_the_z_score():
    """The 7 horizons repeat each target hour; counting them 7x must not look 7x more certain."""
    rng = np.random.default_rng(1)
    ts = _hours("2025-06-02", 4)
    p = pd.Series(rng.uniform(0, 0.4, len(ts)))
    y = pd.Series(rng.uniform(0, 1, len(ts)) < p * 1.3)
    once = calibration_drift(ts, p, y)
    seven = calibration_drift(
        pd.concat([ts] * 7, ignore_index=True),
        pd.concat([p] * 7, ignore_index=True),
        pd.concat([y] * 7, ignore_index=True),
    )
    assert seven["z_calibration"] == pytest.approx(once["z_calibration"])


def test_slot_drift_flags_only_a_significant_drop():
    assert slot_drift(pd.Series([1.0] * 16 + [0.0] * 24), 0.8)["z_slots"] < -DRIFT_Z
    assert slot_drift(pd.Series([1.0] * 30 + [0.0] * 10), 0.8)["z_slots"] > -DRIFT_Z
    assert np.isnan(slot_drift(pd.Series([1.0, 0.0]), None)["z_slots"])


def _market(weeks_ok: int, weeks_drift: int, seed: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hourly D+1 predictions; prices follow them, then become cheap 3x more often."""
    rng = np.random.default_rng(seed)
    ts = _hours("2025-06-02", weeks_ok + weeks_drift)
    hour = ts.dt.tz_convert(config.LOCAL_TZ).dt.hour
    p_nz = np.where(hour.between(9, 17), 0.25, 0.02)
    truth = p_nz * np.where(ts < ts.iloc[0] + pd.Timedelta(weeks=weeks_ok), 1.0, 3.0)
    u = rng.uniform(0, 1, len(ts))
    price = np.where(u < truth / 2, -5.0, np.where(u < truth, 10.0, 80.0))
    predictions = pd.DataFrame(
        {
            "issue_ts": ts.dt.floor("D") - pd.Timedelta(hours=14),
            "horizon_days": 1,
            "target_ts_utc": ts,
            "p_near_zero": p_nz,
            "p_cheap": p_nz / 2,
        }
    )
    prices = pd.DataFrame({"ts_utc": ts, "price_mean": price})
    return predictions, prices


def test_weekly_drift_flags_the_weeks_after_the_market_changes():
    predictions, prices = _market(weeks_ok=6, weeks_drift=6)
    report = weekly_drift(predictions, prices, tau=0.2, window_weeks=3)
    nz = report[report["label"] == "p_near_zero"].reset_index(drop=True)

    assert len(nz) == 12 and set(report["label"]) == {"p_near_zero", "p_cheap"}
    assert not nz.loc[:5, "calibration_drift"].any()  # 6 calibrated weeks
    assert nz.loc[8:, "calibration_drift"].all()  # windows fully inside the drift
    assert (nz.loc[8:, "oe_ratio"] > 2).all()
    assert nz.loc[8:, "reason"].str.contains("more than predicted").all()
    assert (nz.loc[:5, "reason"] == "").all()


def test_drift_refuses_the_test_split(tiny_training_table, tmp_dirs):
    shifted = tiny_training_table.assign(
        issue_ts=tiny_training_table["issue_ts"] + pd.Timedelta(days=700),
        target_ts_utc=tiny_training_table["target_ts_utc"] + pd.Timedelta(days=700),
    )
    io.write(shifted, "training_table")
    with pytest.raises(SystemExit, match="test split"):
        drift.main(["--start", "2026-05-01", "--end", "2026-06-30"])


def test_drift_report_end_to_end(tiny_training_table, tmp_dirs):
    io.write(tiny_training_table, "training_table")
    prices = tiny_training_table.drop_duplicates("target_ts_utc").rename(
        columns={"target_ts_utc": "ts_utc", "y_price": "price_mean"}
    )
    io.write(
        prices.assign(price_min=prices["price_mean"], price_max=prices["price_mean"]),
        "prices_hourly",
    )
    train.main(["--task", "classify"])
    drift.main(["--start", "2025-03-01", "--end", "2025-08-31"])

    report = pd.read_csv(config.REPORTS_DIR / "eval" / "drift_2025-03-01_2025-08-31.csv")
    assert set(report["label"]) == {"p_near_zero", "p_cheap"}
    assert {"oe_ratio", "z_calibration", "slot_hit_rate", "calibration_drift", "reason"} <= set(
        report.columns
    )
    assert report["model_version"].nunique() == 1


def test_model_drift_rows_match_the_dataset_schema_and_skip_unfinished_weeks():
    predictions, prices = _market(weeks_ok=6, weeks_drift=6)
    predictions["model_version"] = "v1"
    # Prices stop mid-way through the last week: that week must not be reported yet.
    prices = prices[prices["ts_utc"] < prices["ts_utc"].max() - pd.Timedelta(days=3)]
    rows = model_drift_rows(predictions, prices, tau=0.2, window_weeks=3)

    assert list(rows.columns) == list(MODEL_DRIFT)
    assert set(rows.groupby("label").size()) == {11}  # 12 weeks, the unfinished one left out
    assert not rows.duplicated(["week_start_utc", "label"]).any()
    assert str(rows["week_start_utc"].dt.tz) == "UTC"
    assert (rows["window_end_utc"] - rows["week_start_utc"]).eq(pd.Timedelta(days=7)).all()
    assert (rows["model_version"] == "v1").all()
    assert rows["drift"].equals(rows["calibration_drift"] | rows["slot_drift"])
    io.check_columns(rows, "model_drift")
