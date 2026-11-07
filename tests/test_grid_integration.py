import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.data.build_grid import grid_from_regional_load
from gridsense.data.build_regional import BIDDING_ZONES, add_regional_features, forecast_grid
from gridsense.data.check_regional_ml_join import join_regional_features, verify_sample
from gridsense.schemas import GRID_HOURLY, PRICES_HOURLY


def test_grid_uses_only_romanian_load_and_preserves_missing_generation():
    regional = pd.DataFrame(
        {
            "country_code": ["BG", "RO", "RO"],
            "ts_utc": pd.to_datetime(
                ["2025-03-27T22:00Z", "2025-03-27T23:00Z", "2025-03-27T22:00Z"], utc=True
            ),
            "load_actual_mw": [5000, 6000, 6100],
        }
    )
    grid = grid_from_regional_load(regional)
    assert grid.dtypes.astype(str).to_dict() == GRID_HOURLY
    assert grid["load_actual_mw"].tolist() == [6100, 6000]
    assert grid["ts_utc"].is_monotonic_increasing
    assert grid[["solar_actual_mw", "wind_actual_mw"]].isna().all().all()

    with pytest.raises(ValueError, match="duplicate"):
        grid_from_regional_load(pd.concat([regional, regional.iloc[[1]]]))
    regional.loc[1, "load_actual_mw"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        grid_from_regional_load(regional)


def test_ml_join_matches_real_contract_on_spring_dst():
    start = pd.Timestamp("2025-03-20", tz=config.LOCAL_TZ).tz_convert("UTC")
    end = pd.Timestamp("2025-03-31", tz=config.LOCAL_TZ).tz_convert("UTC")
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    price = pd.DataFrame(
        {
            "ts_utc": hours,
            "price_mean": 25.0,
            "price_min": 25.0,
            "price_max": 25.0,
        }
    ).astype(PRICES_HOURLY)
    prices = pd.concat(
        [price.assign(country_code=country) for country in BIDDING_ZONES], ignore_index=True
    )
    load = pd.concat(
        [
            pd.DataFrame({"country_code": country, "ts_utc": hours, "load_actual_mw": value})
            for country, value in (("RO", 6000.0), ("HU", 5000.0), ("BG", 4000.0))
        ],
        ignore_index=True,
    )
    grid = grid_from_regional_load(load)
    regional = add_regional_features(forecast_grid(start, end), prices, load)
    joined = verify_sample(price, grid, regional)
    assert len(joined) == 23
    assert joined["f_load_mean_dm1"].eq(6000).all()
    assert joined["f_load_ro_same_hour_d_minus_1"].eq(6000).all()
    assert joined["f_price_spread_ro_hu_d"].eq(0).all()
    assert joined["f_solar_max_dm1"].isna().all()

    keys = ["issue_ts", "target_ts_utc", "horizon_days"]
    with pytest.raises(ValueError, match="unique"):
        join_regional_features(joined[keys], pd.concat([regional, regional.iloc[[0]]]))
    subset, missing = join_regional_features(joined[keys], regional.iloc[0:0])
    assert missing == 23
    assert subset["f_load_ro_same_hour_d_minus_1"].isna().all()
    assert not np.isinf(joined["f_load_mean_dm1"]).any()
