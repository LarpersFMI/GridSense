import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.models.baselines import Climatology, SolarRule
from gridsense.splits import assign_split


def _split(table):
    split = assign_split(table["target_ts_utc"])
    return table[split == "train"], table[split == "val"]


@pytest.fixture
def calendar_table() -> pd.DataFrame:
    """Hourly targets, 3 horizons each; cheap exactly on weekend middays (local time)."""
    # Starts in January so every val month (Mar-Sep) also appears in train.
    target = pd.date_range("2024-01-01", "2025-08-31 23:00", freq="h", tz="UTC")
    local = target.tz_convert(config.LOCAL_TZ)
    cheap = (local.day_of_week >= 5) & (local.hour >= 11) & (local.hour <= 14)
    one = pd.DataFrame(
        {"target_ts_utc": target, "y_price": np.where(cheap, -5.0, 80.0), "f_dummy": 0.0}
    )
    table = pd.concat([one.assign(horizon_days=h) for h in (1, 2, 3)], ignore_index=True)
    table["issue_ts"] = table["target_ts_utc"] - pd.to_timedelta(table["horizon_days"], unit="D")
    table["y_near_zero"] = table["y_price"] <= config.NEAR_ZERO_THRESHOLD_EUR
    table["y_cheap"] = table["y_price"] <= config.CHEAP_THRESHOLD_EUR
    return table


def test_climatology_learns_the_calendar_pattern(calendar_table):
    tr, val = _split(calendar_table)
    out = Climatology().fit(tr).predict(val)

    assert out.index.equals(val.index)
    assert out["price_p50"].isna().all()
    for col, label in (("p_near_zero", "y_near_zero"), ("p_cheap", "y_cheap")):
        assert out[col].between(0, 1).all()
        # Weekend middays score high, everything else low.
        assert out.loc[val[label], col].min() > 0.5
        assert out.loc[~val[label], col].max() < 0.5


def test_climatology_counts_each_target_hour_once(calendar_table):
    tr, _ = _split(calendar_table)
    one_horizon = tr[tr["horizon_days"] == 1]
    a = Climatology().fit(tr).cells
    b = Climatology().fit(one_horizon).cells
    pd.testing.assert_frame_equal(a, b)


def test_solar_rule_scores_fired_hours_higher(tiny_training_table):
    tr, val = _split(tiny_training_table)
    rule = SolarRule(threshold_wm2=0.7, ghi_column="f_solar", day_off_columns=("f_weekend",))
    out = rule.fit(tr).predict(val)

    fired = rule.fires(val)
    assert fired.any() and not fired.all()
    for col in ("p_near_zero", "p_cheap"):
        assert out[col].between(0, 1).all()
        # A yes/no rule gives exactly one probability per outcome of the rule.
        assert out.loc[fired, col].nunique() == 1
        assert out.loc[fired, col].iloc[0] > out.loc[~fired, col].iloc[0]


def test_solar_rule_needs_weather_columns(tiny_training_table):
    with pytest.raises(ValueError, match="f_ghi_mean"):
        SolarRule().fit(tiny_training_table)
