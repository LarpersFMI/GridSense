import pandas as pd
import pytest

from gridsense import config, io
from gridsense.features.build import _local, build_training_table
from gridsense.schemas import FEATURE_PREFIX
from gridsense.synthetic import market

ISSUE_DATE = pd.Timestamp("2024-03-15")


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return market.generate("2024-01-01", "2024-04-30")


def _build(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return build_training_table(t["prices_hourly"], t["grid_hourly"], t["weather_fc"], t["calendar"])


def _rows_for_issue(table: pd.DataFrame, issue_date: pd.Timestamp) -> pd.DataFrame:
    issue_ts = (issue_date + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(config.LOCAL_TZ)
    return table[table["issue_ts"] == issue_ts.tz_convert("UTC")].reset_index(drop=True)


def _features(df: pd.DataFrame) -> pd.DataFrame:
    return df[[c for c in df.columns if c.startswith(FEATURE_PREFIX)]]


def _shift_prices(prices: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    out = prices.copy()
    for col in ("price_mean", "price_min", "price_max"):
        out.loc[mask, col] += 500.0
    return out


def test_features_only_use_data_known_at_issue_time(tables):
    perturbed = dict(tables)
    price_date = _local(tables["prices_hourly"]["ts_utc"])["date"]
    perturbed["prices_hourly"] = _shift_prices(tables["prices_hourly"], price_date > ISSUE_DATE)

    grid = tables["grid_hourly"].copy()
    grid_date = _local(grid["ts_utc"])["date"]
    grid.loc[grid_date >= ISSUE_DATE, ["load_actual_mw", "solar_actual_mw", "wind_actual_mw"]] *= 2
    perturbed["grid_hourly"] = grid

    weather = tables["weather_fc"].copy()
    weather.loc[weather["issue_date"] > ISSUE_DATE, ["ghi_wm2", "temp_c"]] += 100.0
    perturbed["weather_fc"] = weather

    base = _rows_for_issue(_build(tables), ISSUE_DATE)
    changed = _rows_for_issue(_build(perturbed), ISSUE_DATE)

    assert len(base) > 0
    pd.testing.assert_frame_equal(_features(base), _features(changed))
    assert not base["y_price"].equals(changed["y_price"]), "perturbation should reach the labels"


def test_prices_of_issue_day_are_used(tables):
    """Sensitivity check, so the leakage test can't pass by ignoring prices altogether."""
    perturbed = dict(tables)
    price_date = _local(tables["prices_hourly"]["ts_utc"])["date"]
    perturbed["prices_hourly"] = _shift_prices(tables["prices_hourly"], price_date == ISSUE_DATE)

    base = _features(_rows_for_issue(_build(tables), ISSUE_DATE))
    changed = _features(_rows_for_issue(_build(perturbed), ISSUE_DATE))
    assert (base[f"{FEATURE_PREFIX}price_same_hour_d"] != changed[f"{FEATURE_PREFIX}price_same_hour_d"]).all()


def test_table_shape_and_dst(tables):
    table = _build(tables)
    io.check_columns(table, "training_table")
    assert set(table["horizon_days"]) == set(config.HORIZONS_DAYS)
    assert not table.duplicated(["issue_ts", "horizon_days", "target_ts_utc"]).any()

    # 2024-03-31 is the spring DST switch in Romania: 23 local hours.
    rows = _rows_for_issue(table, pd.Timestamp("2024-03-30"))
    assert (rows["horizon_days"] == 1).sum() == 23
    assert rows[f"{FEATURE_PREFIX}ghi_mean"].notna().all()
