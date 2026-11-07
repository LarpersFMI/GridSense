import itertools

import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.features.weather_grid import (
    GRID_PREFIX,
    grid_features,
    grid_locations,
    join_grid_features,
)
from gridsense.models.error_analysis import (
    MAX_SLOTS_PER_DAY,
    MONTHLY_BUDGET_HOURS,
    budget_metrics,
    plan_month,
    price_breakdown,
)

ISSUE_DATE = pd.Timestamp("2025-06-02")
TARGET = pd.Timestamp("2025-06-04 09:00", tz="UTC")


def _weather(lead_days: tuple[int, ...] = (2,), ghi: float = 500.0) -> pd.DataFrame:
    target_day = TARGET.tz_convert(config.LOCAL_TZ).tz_localize(None).normalize()
    rows = []
    for lead in lead_days:
        for i, point in enumerate(grid_locations()["ro"]):
            rows.append({"issue_date": target_day - pd.Timedelta(days=lead), "target_ts_utc": TARGET,
                         "lead_days": lead, "location": point, "ghi_wm2": ghi + i,
                         "cloud_cover_pct": 10.0, "wind100_ms": 5.0, "temp_c": 20.0})
    return pd.DataFrame(rows)


def test_country_means_use_only_the_matching_issue_and_lead():
    weather = _weather(lead_days=(2, 3))
    features = grid_features(weather, ("ro",)).set_index(["horizon_days"])
    n = len(grid_locations()["ro"])
    assert features.loc[2, f"{GRID_PREFIX}ro_ghi_mean"] == pytest.approx(500 + (n - 1) / 2)
    assert features.loc[2, f"{GRID_PREFIX}ro_ghi_std"] > 0
    # Changing an older forecast must not change the newer issue's features.
    changed = weather.copy()
    changed.loc[changed.lead_days.eq(3), "ghi_wm2"] = 0.0
    after = grid_features(changed, ("ro",)).set_index(["horizon_days"])
    pd.testing.assert_series_equal(after.loc[2], features.loc[2])
    assert after.loc[3, f"{GRID_PREFIX}ro_ghi_mean"] == 0.0


def test_missing_point_values_give_nan_and_missing_points_are_rejected():
    weather = _weather()
    weather.loc[0, "ghi_wm2"] = np.nan
    features = grid_features(weather, ("ro",))
    assert features[f"{GRID_PREFIX}ro_ghi_mean"].isna().all()
    assert features[f"{GRID_PREFIX}ro_temp_mean"].notna().all()
    with pytest.raises(ValueError, match="missing ro points"):
        grid_features(weather.iloc[1:], ("ro",))


def test_rejects_observed_weather_leads():
    with pytest.raises(ValueError, match="D\\+1"):
        grid_features(_weather().assign(lead_days=0), ("ro",))


def test_join_preserves_rows_and_matches_local_issue_date():
    features = grid_features(_weather(), ("ro",))
    issue = (_weather().issue_date[0] + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(
        config.LOCAL_TZ).tz_convert("UTC")
    table = pd.DataFrame({"issue_ts": [issue, issue], "target_ts_utc": [TARGET, TARGET + pd.Timedelta(hours=1)],
                          "horizon_days": [2, 2], "y_price": [1.0, 2.0], "f_hour": [12, 13]}, index=[7, 3])
    joined = join_grid_features(table, features)
    pd.testing.assert_frame_equal(joined[table.columns], table)
    assert joined.loc[7, f"{GRID_PREFIX}ro_cloud_mean"] == 10.0
    assert np.isnan(joined.loc[3, f"{GRID_PREFIX}ro_cloud_mean"])
    with pytest.raises(ValueError, match="already exist"):
        join_grid_features(joined, features)


def test_slot_plan_respects_budget_daily_cap_and_overlap():
    days = pd.date_range("2025-06-01", periods=31).date
    frame = pd.DataFrame([(d, h, 1.0) for d in days for h in range(9, 18)], columns=["date", "hour", "score"])
    chosen = plan_month(frame)
    assert sum(length for _, _, length in chosen) <= MONTHLY_BUDGET_HOURS
    per_day = pd.Series([d for d, _, _ in chosen]).value_counts()
    assert per_day.max() <= MAX_SLOTS_PER_DAY
    for day in per_day.index:
        blocks = sorted((s, s + n) for d, s, n in chosen if d == day)
        assert all(a_end <= b_start for (_, a_end), (b_start, _) in itertools.pairwise(blocks))
        assert all(9 <= s and e <= 18 for s, e in blocks)


def test_oracle_budget_announces_only_cheap_hours_when_available():
    ts = pd.date_range("2025-06-01 06:00", periods=24 * 30, freq="h", tz="UTC")
    local_hour = ts.tz_convert(config.LOCAL_TZ).hour
    price = np.where((local_hour >= 11) & (local_hour < 15), -5.0, 80.0)
    rows = pd.DataFrame({"target_ts_utc": ts, "horizon_days": 1, "y_price": price})
    result = budget_metrics(rows, {"oracle": -rows["y_price"], "worst": rows["y_price"]}).set_index(
        ["model", "horizon"])
    assert result.loc[("oracle", "all"), "slot_hit_rate"] == 1.0
    assert result.loc[("oracle", "all"), "precision_at_budget"] == 1.0
    assert result.loc[("worst", "all"), "slot_hit_rate"] == 0.0
    assert result.loc[("oracle", "all"), "announced_hours"] <= MONTHLY_BUDGET_HOURS


def test_error_shares_sum_to_one_per_dimension():
    ts = pd.date_range("2025-06-01", periods=48, freq="h", tz="UTC")
    rows = pd.DataFrame({"target_ts_utc": ts, "horizon_days": np.tile([1, 2], 24),
                         "y_price": np.linspace(-10, 200, 48), "f_is_holiday": 0,
                         "f_is_weekend": 0})
    pred = pd.DataFrame({"price_p10": rows.y_price - 10, "price_p50": rows.y_price + 3,
                         "price_p90": rows.y_price + 10}, index=rows.index)
    out = price_breakdown(rows, {"m": pred})
    assert out.groupby("dimension").abs_error_share.sum().round(9).eq(1).all()
    assert out.bias.round(9).eq(3).all()
