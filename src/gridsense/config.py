import os
from pathlib import Path

import pandas as pd

# "fake" lets every team build against synthetic data before the real data exists.
DATA_MODE = os.getenv("GRIDSENSE_DATA", "real")
if DATA_MODE not in ("real", "fake"):
    raise ValueError(f"GRIDSENSE_DATA must be 'real' or 'fake', got {DATA_MODE!r}")

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / ("processed" if DATA_MODE == "real" else "fake")
SYNTHETIC_DIR = DATA_DIR / "synthetic"
MODELS_DIR = ROOT / "models" / DATA_MODE
REPORTS_DIR = ROOT / "reports" / DATA_MODE

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

# Ordered by resident population in the 2021 Romanian census.
# Values are WGS84 (latitude, longitude); keys match weather_fc.location.
TOP_20_WEATHER_POINTS: dict[str, tuple[float, float]] = {
    "bucuresti": WEATHER_POINTS["bucuresti"],
    "cluj_napoca": (46.76667, 23.6),
    "iasi": (47.16667, 27.6),
    "constanta": WEATHER_POINTS["constanta"],
    "timisoara": WEATHER_POINTS["timisoara"],
    "brasov": (45.64861, 25.60613),
    "craiova": WEATHER_POINTS["craiova"],
    "galati": (45.43687, 28.05028),
    "oradea": (47.0458, 21.91833),
    "ploiesti": (44.95, 26.01667),
    "braila": (45.27152, 27.97429),
    "arad": (46.18333, 21.31667),
    "pitesti": (44.85, 24.86667),
    "bacau": (46.56718, 26.91384),
    "sibiu": (45.8, 24.15),
    "targu_mures": (46.54245, 24.55747),
    "baia_mare": (47.65729, 23.56808),
    "buzau": (45.15, 26.83333),
    "ramnicu_valcea": (45.1, 24.36667),
    "satu_mare": (47.79926, 22.86255),
}

RANDOM_SEED = 42
