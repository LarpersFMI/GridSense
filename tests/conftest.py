import numpy as np
import pandas as pd
import pytest

from gridsense import config


@pytest.fixture
def tiny_training_table() -> pd.DataFrame:
    """Small table spanning train and val, with prices driven by two features."""
    rng = np.random.default_rng(0)
    target = pd.date_range("2024-06-01", "2025-08-31", freq="6h", tz="UTC")
    n = len(target)
    solar = rng.uniform(0, 1, n)
    weekend = rng.integers(0, 2, n)
    price = 100 - 120 * solar - 20 * weekend + rng.normal(0, 15, n)
    return pd.DataFrame(
        {
            "issue_ts": target - pd.Timedelta(days=1),
            "target_ts_utc": target,
            "horizon_days": 1,
            "y_price": price,
            "y_near_zero": price <= config.NEAR_ZERO_THRESHOLD_EUR,
            "y_cheap": price <= config.CHEAP_THRESHOLD_EUR,
            "f_solar": solar,
            "f_weekend": weekend,
        }
    )


@pytest.fixture
def tmp_dirs(tmp_path, monkeypatch):
    for name in ("PROCESSED_DIR", "MODELS_DIR", "REPORTS_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    return tmp_path
