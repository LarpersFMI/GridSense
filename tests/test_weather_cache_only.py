import pandas as pd
import pytest

from gridsense.data.weather import fetch_weather_forecasts
from gridsense.features.weather_grid import fetch_grid


def test_cache_only_missing_request_never_contacts_api(tmp_path, monkeypatch):
    monkeypatch.setattr("requests.Session.get", lambda *args, **kwargs: pytest.fail("Network access"))
    start = pd.Timestamp("2025-06-01", tz="UTC")
    with pytest.raises(FileNotFoundError, match="Missing cached weather request"):
        fetch_weather_forecasts(start, start + pd.Timedelta(days=1),
                                cache_dir=tmp_path, cache_only=True)


def test_grid_cache_only_skips_download_and_pacing(monkeypatch):
    from gridsense.features import weather_grid

    calls = []

    def fetch(start, end, **kwargs):
        calls.append(kwargs)
        raise FileNotFoundError("missing fixture cache")

    monkeypatch.setattr(weather_grid, "fetch_weather_forecasts", fetch)
    monkeypatch.setattr(weather_grid.time, "sleep", lambda *args: pytest.fail("Unexpected pacing"))
    start = pd.Timestamp("2025-06-01", tz="UTC")
    with pytest.raises(FileNotFoundError):
        fetch_grid(start, start + pd.Timedelta(days=1), cache_only=True)
    assert len(calls) == 1 and calls[0]["cache_only"] is True