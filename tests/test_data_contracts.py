import importlib.util

import pandas as pd
import pytest

from gridsense import config, io
from gridsense.data.calendar import build_calendar
from gridsense.features.build import _weather_features, build_training_table
from gridsense.schemas import COUNTRY_CALENDAR, WEATHER_FC, WEATHER_HOURLY


def test_observed_weather_has_a_separate_contract_and_cannot_enter_forecast_features():
    observed = pd.DataFrame(columns=WEATHER_HOURLY)
    io.check_columns(observed, "weather_hourly")
    with pytest.raises(ValueError, match="weather_fc: missing columns"):
        io.check_columns(observed, "weather_fc")
    with pytest.raises(ValueError, match="weather_fc: missing columns"):
        _weather_features(observed)
    # Legacy export extras still do not supply the irradiance and 100m wind forecast fields.
    legacy = observed.assign(issue_date=pd.NaT, lead_days=0)
    with pytest.raises(ValueError, match="weather_fc: missing columns"):
        _weather_features(legacy)


def test_fabricated_zero_day_weather_is_rejected_even_if_columns_are_added():
    weather = pd.DataFrame({c: [None] for c in WEATHER_FC})
    weather["lead_days"] = 0
    with pytest.raises(ValueError, match="not observed weather"):
        _weather_features(weather)


def test_minimal_ml_calendar_and_enriched_country_exports_coexist():
    calendar = build_calendar(config.TRAIN_START.date(),
                              (config.TRAIN_START + pd.Timedelta(days=1)).date())
    io.check_columns(calendar, "calendar")
    country = calendar.assign(country="Romania", is_working_holiday=False, split="Train")
    for name in ("calendar_romania", "calendar_hungary", "calendar_bulgaria", "calendar_moldova"):
        io.check_columns(country, name)
    assert set(COUNTRY_CALENDAR) == set(country.columns)


def test_calendar_build_does_not_require_ignored_raw_holiday_exports(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "absent-raw")
    calendar = build_calendar(config.TRAIN_START.date(), config.TRAIN_START.date())
    io.check_columns(calendar, "calendar")
    assert not calendar.is_working_holiday.any()


def test_ml_calendar_rejects_non_romanian_and_duplicate_target_hours():
    calendar = build_calendar(config.TRAIN_START.date(), config.TRAIN_START.date())
    prices = pd.DataFrame({"ts_utc": calendar.ts_utc, "price_mean": 50.0})
    with pytest.raises(ValueError, match="must be Romanian"):
        build_training_table(prices, None, None, calendar.assign(country="Hungary"))
    with pytest.raises(ValueError, match="one row per UTC hour"):
        build_training_table(prices, None, None, pd.concat([calendar, calendar]))


def test_observed_generator_preserves_forecast_table_and_does_not_invent_issue_times(
    tmp_dirs, monkeypatch
):
    raw_dir = tmp_dirs / "raw"
    raw_dir.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw_dir)
    raw = pd.DataFrame({"time": ["2025-04-01T12:00Z"], "location": ["bucuresti"],
                        "country": ["Romania"], "latitude": [44.43], "longitude": [26.11],
                        "temperature_2m": [18.0], "relative_humidity_2m": [50.0],
                        "precipitation": [0.0], "rain": [0.0], "snowfall": [0.0],
                        "surface_pressure": [1000.0], "cloud_cover": [20.0],
                        "wind_speed_10m": [3.0], "wind_direction_10m": [180.0], "split": ["Validation"]})
    raw.to_csv(raw_dir / "weather_hourly.csv", index=False)
    path = config.ROOT / "data/interim/generate_weather_parquet.py"
    spec = importlib.util.spec_from_file_location("observed_weather_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    forecast = pd.DataFrame(columns=WEATHER_FC)
    io.write(forecast, "weather_fc")
    module.process_raw_weather_to_parquet()
    observed = io.read("weather_hourly")
    assert "issue_date" not in observed and "lead_days" not in observed
    assert observed.source.eq("open_meteo_archive_observed").all()
    pd.testing.assert_frame_equal(io.read("weather_fc"), forecast)