import numpy as np
import pandas as pd
import pytest

from gridsense import config, io
from gridsense.data.weather import DEFAULT_LOCATIONS
from gridsense.features import build
from gridsense.features.forecast_engineering import (
    DRY_AIR_GAS_CONSTANT,
    PREFIX,
    join_engineered_features,
    price_features,
    solar_potential,
    weather_features,
)


@pytest.fixture
def inputs():
    targets = pd.date_range("2024-01-15", periods=24, freq="h", tz=config.LOCAL_TZ)
    points, rows = [], []
    for horizon in (1, 2):
        issue_date = pd.Timestamp("2024-01-15") - pd.Timedelta(days=horizon)
        issue = (issue_date + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(config.LOCAL_TZ)
        for target in targets:
            rows.append({"issue_ts": issue.tz_convert("UTC"),
                         "target_ts_utc": target.tz_convert("UTC"), "horizon_days": horizon,
                         "y_price": 30.0, "y_near_zero": False, "y_cheap": False,
                         "f_control": 7.0, "data_quality": "ok"})
            for i, location in enumerate(DEFAULT_LOCATIONS):
                points.append({
                    "issue_date": issue_date, "target_ts_utc": target.tz_convert("UTC"),
                    "lead_days": horizon, "location": location,
                    "ghi_wm2": 300.0, "cloud_cover_pct": 20.0, "wind100_ms": 8.0,
                    "temp_c": (10.0, 30.0, 18.0, 22.0)[i], "pressure_hpa": 1013.25,
                    "wind10_ms": float(2 * (i + 1)), "wind_dir_deg": float(90 * i),
                })
    training = pd.DataFrame(rows)
    training.index = pd.Index(101 + 3 * np.arange(len(training)), name="original_index")
    times = pd.date_range("2024-01-08", periods=24 * 10, freq="h", tz="UTC")
    prices = pd.DataFrame({"ts_utc": times, "price_mean": np.arange(len(times), dtype=float),
                           "price_min": 0.0, "price_max": 400.0})
    return training, pd.DataFrame(points), prices


def _new(table):
    return table.filter(regex=f"^{PREFIX}")


def test_preserves_full_control_and_inputs_without_io_reads(inputs, monkeypatch):
    training, weather, prices = inputs
    before = [frame.copy(deep=True) for frame in inputs]
    monkeypatch.setattr(io, "read", lambda *args: pytest.fail("Must not read observed tables/ranking"))
    result = join_engineered_features(training, weather, prices)
    pd.testing.assert_frame_equal(result[training.columns], training)
    for frame, original in zip(inputs, before, strict=True):
        pd.testing.assert_frame_equal(frame, original)
    assert len(_new(result).columns) == 51
    assert not result.duplicated(["issue_ts", "target_ts_utc", "horizon_days"]).any()
    assert result[f"{PREFIX}missing_weather"].eq(0).all()


def test_physical_units_and_nonlinear_transforms_precede_point_mean(inputs):
    _, weather, _ = inputs
    result = weather_features(weather).iloc[0]
    density = 101325 / (DRY_AIR_GAS_CONSTANT * (10 + 273.15))
    assert result[f"{PREFIX}air_density_kgm3_bucuresti"] == pytest.approx(density)
    assert result[f"{PREFIX}wind10_power_density_proxy_wm2_bucuresti"] == pytest.approx(
        0.5 * density * 2 ** 3)
    assert result[f"{PREFIX}wind10_u_ms_bucuresti"] == pytest.approx(0, abs=1e-12)
    assert result[f"{PREFIX}wind10_v_ms_bucuresti"] == pytest.approx(-2)
    assert result[f"{PREFIX}wind10_u_ms_constanta"] == pytest.approx(-4)
    assert result[f"{PREFIX}heating_degree_c_mean"] == pytest.approx(2)
    assert result[f"{PREFIX}cooling_degree_c_mean"] == pytest.approx(2)
    powers = [0.5 * 101325 / (DRY_AIR_GAS_CONSTANT * (temp + 273.15)) * speed ** 3
              for temp, speed in ((10, 2), (30, 4), (18, 6), (22, 8))]
    assert result[f"{PREFIX}wind10_power_density_proxy_wm2_mean"] == pytest.approx(np.mean(powers))
    assert result[f"{PREFIX}wind10_power_density_proxy_wm2_mean"] != pytest.approx(
        0.5 * np.mean([101325 / (DRY_AIR_GAS_CONSTANT * (t + 273.15))
                      for t in (10, 30, 18, 22)]) * 5 ** 3)


def test_solar_geometry_is_dimensionless_and_timezone_invariant():
    target = pd.Series(pd.to_datetime(["2024-06-21T00:00Z", "2024-06-21T10:00Z"]))
    latitude, longitude = pd.Series([44.43, 44.43]), pd.Series([26.11, 26.11])
    utc = solar_potential(target, latitude, longitude)
    local = solar_potential(target.dt.tz_convert(config.LOCAL_TZ), latitude, longitude)
    pd.testing.assert_series_equal(utc, local)
    assert utc.iloc[0] == 0
    assert 0.8 < utc.iloc[1] <= 1


def test_cloud_proxy_uses_forecast_clouds_not_observed_values(inputs):
    _, weather, _ = inputs
    result = weather_features(weather)
    for location in DEFAULT_LOCATIONS:
        np.testing.assert_allclose(result[f"{PREFIX}solar_cloud_proxy_{location}"],
                                   result[f"{PREFIX}solar_potential_{location}"] * 0.8)


@pytest.mark.parametrize("cloud", [0.0, 100.0])
def test_clear_and_overcast_cloud_proxy_bounds(inputs, cloud):
    _, weather, _ = inputs
    result = weather_features(weather.assign(cloud_cover_pct=cloud))
    np.testing.assert_allclose(result[f"{PREFIX}solar_cloud_proxy_mean"],
                               result[f"{PREFIX}solar_potential_mean"] * (1 - cloud / 100))


def test_thermal_bases_come_from_configuration(inputs, monkeypatch):
    _, weather, _ = inputs
    monkeypatch.setattr(config, "HEATING_BASE_C", 20.0)
    monkeypatch.setattr(config, "COOLING_BASE_C", 24.0)
    result = weather_features(weather).iloc[0]
    assert result[f"{PREFIX}heating_degree_c_bucuresti"] == 10
    assert result[f"{PREFIX}cooling_degree_c_constanta"] == 6


def test_missing_point_is_not_hidden_by_a_partial_mean(inputs):
    training, weather, prices = inputs
    partial = weather.loc[weather.location.ne("constanta")].copy()
    result = join_engineered_features(training, partial, prices)
    pd.testing.assert_frame_equal(result[training.columns], training)
    assert result[f"{PREFIX}heating_degree_c_constanta"].isna().all()
    assert result[f"{PREFIX}heating_degree_c_mean"].isna().all()
    assert result[f"{PREFIX}heating_degree_c_bucuresti"].notna().all()
    assert result[f"{PREFIX}missing_weather"].eq(1).all()


def test_missing_extra_archive_fields_stay_missing(inputs):
    training, weather, prices = inputs
    core = weather.drop(columns=["pressure_hpa", "wind10_ms", "wind_dir_deg"])
    result = join_engineered_features(training, core, prices)
    assert result.filter(regex=f"^{PREFIX}(air_density|wind10)").isna().all().all()
    assert result[f"{PREFIX}heating_degree_c_mean"].notna().all()
    assert result[f"{PREFIX}missing_weather"].eq(1).all()


def test_all_forecast_values_missing_do_not_fill_weather_with_geometry(inputs):
    training, weather, prices = inputs
    missing = weather.copy()
    numeric = ["ghi_wm2", "cloud_cover_pct", "wind100_ms", "temp_c",
               "pressure_hpa", "wind10_ms", "wind_dir_deg"]
    missing[numeric] = np.nan
    result = join_engineered_features(training, missing, prices)
    assert result[f"{PREFIX}solar_potential_mean"].notna().all()
    assert result[f"{PREFIX}solar_cloud_proxy_mean"].isna().all()
    assert result[f"{PREFIX}heating_degree_c_mean"].isna().all()
    assert result[f"{PREFIX}missing_weather"].eq(1).all()


def test_missing_cloud_is_not_filled_even_at_night(inputs):
    training, weather, prices = inputs
    cloudy = weather.assign(cloud_cover_pct=np.nan)
    result = join_engineered_features(training, cloudy, prices)
    assert result.filter(regex=f"^{PREFIX}solar_cloud_proxy").isna().all().all()
    assert result[f"{PREFIX}solar_potential_mean"].notna().all()
    assert result[f"{PREFIX}missing_weather"].eq(1).all()


@pytest.mark.parametrize("empty", [False, True])
def test_unmatched_forecast_keys_and_missing_horizons_are_retained(inputs, empty):
    training, weather, prices = inputs
    missing = weather.iloc[:0].copy() if empty else weather.loc[weather.lead_days.eq(1)].copy()
    result = join_engineered_features(training, missing, prices)
    pd.testing.assert_frame_equal(result[training.columns], training)
    absent = result if empty else result.loc[result.horizon_days.eq(2)]
    assert absent[f"{PREFIX}heating_degree_c_mean"].isna().all()
    assert absent[f"{PREFIX}missing_weather"].eq(1).all()
    assert absent[f"{PREFIX}hour_sin"].notna().all()


def test_same_target_other_issue_forecasts_do_not_change_selected_issue(inputs):
    training, weather, prices = inputs
    selected = training.loc[training.horizon_days.eq(2)].copy()
    changed = weather.copy()
    changed.loc[changed.lead_days.eq(1), "temp_c"] = 50
    before = join_engineered_features(selected, weather, prices)
    after = join_engineered_features(selected, changed, prices)
    pd.testing.assert_frame_equal(before, after)
    changed.loc[changed.lead_days.eq(2), "temp_c"] = 50
    affected = join_engineered_features(selected, changed, prices)
    assert not before[f"{PREFIX}cooling_degree_c_mean"].equals(
        affected[f"{PREFIX}cooling_degree_c_mean"])


def test_future_prices_and_target_labels_cannot_change_engineered_features(inputs):
    training, weather, prices = inputs
    selected = training.loc[training.horizon_days.eq(2)].copy()
    changed = prices.copy()
    changed.loc[changed.ts_utc.ge(selected.issue_ts.iloc[0]), "price_mean"] += 500
    altered_labels = selected.assign(y_price=1000.0, y_near_zero=True, y_cheap=True)
    before = join_engineered_features(selected, weather, prices)
    after = join_engineered_features(altered_labels, weather, changed)
    pd.testing.assert_frame_equal(_new(before), _new(after))


def test_price_windows_are_anchored_to_issue_and_require_every_elapsed_hour(inputs):
    training, _, prices = inputs
    result = price_features(training, prices)
    issue = training.issue_ts.iloc[0]
    known = prices.set_index("ts_utc").loc[
        pd.date_range(issue - pd.Timedelta(hours=3), periods=3, freq="h"), "price_mean"]
    assert result.iloc[0][f"{PREFIX}price_recent_mean_3h"] == known.mean()
    assert result.iloc[0][f"{PREFIX}price_recent_std_3h"] == known.std()
    gap = prices.loc[prices.ts_utc.ne(issue - pd.Timedelta(hours=2))].copy()
    missing = price_features(training, gap)
    assert pd.isna(missing.iloc[0][f"{PREFIX}price_recent_mean_3h"])
    assert pd.isna(missing.iloc[0][f"{PREFIX}price_recent_std_3h"])


def test_future_different_horizon_has_identical_issue_time_price_windows(inputs):
    training, _, prices = inputs
    selected = training.loc[training.horizon_days.eq(1)].copy()
    later = selected.copy()
    later["target_ts_utc"] += pd.Timedelta(days=1)
    later["horizon_days"] += 1
    pd.testing.assert_frame_equal(price_features(selected, prices), price_features(later, prices))


def test_price_memory_before_history_start_is_missing(inputs):
    training, _, prices = inputs
    future_history = prices.loc[prices.ts_utc.ge(training.issue_ts.max())].copy()
    assert price_features(training, future_history).isna().all().all()


@pytest.mark.parametrize(("day", "hours"), [("2024-03-31", 23), ("2024-10-27", 25)])
def test_dst_utc_keys_and_elapsed_price_windows_remain_unambiguous(inputs, day, hours):
    _, weather, _ = inputs
    start = pd.Timestamp(day, tz=config.LOCAL_TZ)
    end = start + pd.DateOffset(days=1)
    target = pd.date_range(start, end, freq="h", inclusive="left").tz_convert("UTC")
    issue = (pd.Timestamp(day) - pd.Timedelta(days=1)
             + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(config.LOCAL_TZ)
    training = pd.DataFrame({"issue_ts": issue.tz_convert("UTC"), "target_ts_utc": target,
                             "horizon_days": 1, "f_control": 1.0})
    timestamps = pd.date_range(issue.tz_convert("UTC") - pd.Timedelta(hours=30), periods=31, freq="h")
    prices = pd.DataFrame({"ts_utc": timestamps, "price_mean": np.arange(31, dtype=float),
                           "price_min": 0.0, "price_max": 50.0})
    result = join_engineered_features(training, weather.iloc[:0].copy(), prices)
    assert len(result) == hours
    pd.testing.assert_series_equal(result.target_ts_utc, training.target_ts_utc)
    assert result[f"{PREFIX}price_recent_mean_3h"].eq(28.0).all()
    assert result[f"{PREFIX}missing_weather"].eq(1).all()
    latitude, longitude = pd.Series(44.43, index=result.index), pd.Series(26.11, index=result.index)
    pd.testing.assert_series_equal(
        solar_potential(result.target_ts_utc, latitude, longitude),
        solar_potential(result.target_ts_utc.dt.tz_convert(config.LOCAL_TZ), latitude, longitude),
    )
    # A price window issued on the transition day itself uses distinct elapsed UTC hours.
    dst_issue = (pd.Timestamp(day) + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_localize(config.LOCAL_TZ)
    prices["ts_utc"] += dst_issue.tz_convert("UTC") - issue.tz_convert("UTC")
    dst_memory = price_features(training.assign(issue_ts=dst_issue.tz_convert("UTC")), prices)
    assert dst_memory[f"{PREFIX}price_recent_mean_3h"].eq(28.0).all()


@pytest.mark.parametrize("kind", ["observed", "duplicate", "wrong_day", "late_available"])
def test_rejects_unusable_forecast_provenance(inputs, kind):
    training, weather, prices = inputs
    changed = weather.copy()
    message = {"observed": "not observations", "duplicate": "Duplicate weather",
               "wrong_day": "horizon does not match", "late_available": "after the issue cutoff"}
    if kind == "observed":
        changed["source"] = "open_meteo_archive_observed"
    elif kind == "duplicate":
        changed = pd.concat([changed, changed.iloc[[0]]], ignore_index=True)
    elif kind == "wrong_day":
        changed["issue_date"] += pd.Timedelta(days=1)
    else:
        changed["assumed_available_by_utc"] = (
            changed["issue_date"] + pd.Timedelta(hours=config.ISSUE_HOUR + 1)
        ).dt.tz_localize(config.LOCAL_TZ).dt.tz_convert("UTC")
    with pytest.raises(ValueError, match=message[kind]):
        join_engineered_features(training, changed, prices)


@pytest.mark.parametrize("kind", ["duplicate", "repeated", "off_cutoff", "duplicate_prices",
                                  "wrong_horizon"])
def test_rejects_invalid_training_or_price_keys(inputs, kind):
    training, weather, prices = inputs
    message = {"duplicate": "Duplicate training", "repeated": "already exist",
               "off_cutoff": "configured daily issue", "duplicate_prices": "unique UTC",
               "wrong_horizon": "Training horizon does not match"}
    if kind == "duplicate":
        training = pd.concat([training, training.iloc[[0]]])
    elif kind == "repeated":
        training = join_engineered_features(training, weather, prices)
    elif kind == "off_cutoff":
        training = training.assign(issue_ts=training.issue_ts + pd.Timedelta(minutes=30))
    elif kind == "wrong_horizon":
        training = training.assign(horizon_days=7)
    else:
        prices = pd.concat([prices, prices.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match=message[kind]):
        join_engineered_features(training, weather, prices)


@pytest.mark.parametrize("enabled", [False, True])
def test_cli_engineering_is_explicit_opt_in(inputs, monkeypatch, enabled):
    training, weather, prices = inputs
    monkeypatch.setattr(build, "build_training_table", lambda *args, **kwargs: training.copy())
    monkeypatch.setattr(build, "_read_optional", lambda name: None)
    monkeypatch.setattr(io, "read", lambda name: {
        "prices_hourly": prices, "weather_fc": weather, "calendar": pd.DataFrame(),
    }[name])
    written = []
    monkeypatch.setattr(io, "write", lambda frame, name: written.append((frame, name)))
    build.main(["--forecast-engineered"] if enabled else [])
    result, name = written[0]
    assert name == "training_table"
    pd.testing.assert_frame_equal(result[training.columns], training)
    assert bool(len(_new(result).columns)) == enabled