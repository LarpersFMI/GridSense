from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"

BIDDING_ZONE = "10YRO-TEL------P"
LOCAL_TZ = "Europe/Bucharest"

TRAIN_START = pd.Timestamp("2023-01-01", tz=LOCAL_TZ)
TRAIN_END = pd.Timestamp("2025-02-28 23:00", tz=LOCAL_TZ)
VAL_START = pd.Timestamp("2025-03-01", tz=LOCAL_TZ)
VAL_END = pd.Timestamp("2025-09-30 23:00", tz=LOCAL_TZ)
TEST_START = pd.Timestamp("2026-03-01", tz=LOCAL_TZ)
TEST_END = pd.Timestamp("2026-10-31 23:00", tz=LOCAL_TZ)

ISSUE_HOUR = 10
HORIZONS_DAYS = range(1, 8)

CHEAP_THRESHOLD_EUR = 0.0
NEAR_ZERO_THRESHOLD_EUR = 20.0
QUANTILES = (0.1, 0.5, 0.9)

WEATHER_POINTS = {
    "bucuresti": (44.43, 26.10),
    "constanta": (44.18, 28.63),
    "craiova": (44.32, 23.80),
    "timisoara": (45.76, 21.23),
}

RANDOM_SEED = 42
