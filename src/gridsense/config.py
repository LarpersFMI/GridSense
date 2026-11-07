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
    "bucuresti": (44.43, 26.11, "Romania"),
    "cluj_napoca": (46.77, 23.62, "Romania"),
    "iasi": (47.16, 27.60, "Romania"),
    "constanta": (44.18, 28.65, "Romania"),
    "timisoara": (45.75, 21.23, "Romania"),
    "brasov": (45.66, 25.60, "Romania"),
    "craiova": (44.33, 23.79, "Romania"),
    "galati": (45.44, 28.01, "Romania"),
    "oradea": (47.05, 21.92, "Romania"),
    "ploiesti": (44.94, 26.01, "Romania"),
    "braila": (45.27, 27.96, "Romania"),
    "arad": (46.19, 21.31, "Romania"),
    "pitesti": (44.86, 24.87, "Romania"),
    "bacau": (46.57, 26.91, "Romania"),
    "sibiu": (45.80, 24.13, "Romania"),
    "targu_mures": (46.55, 24.56, "Romania"),
    "baia_mare": (47.66, 23.59, "Romania"),
    "buzau": (45.15, 26.83, "Romania"),
    "ramnicu_valcea": (45.10, 24.37, "Romania"),
    "satu_mare": (47.79, 22.89, "Romania"),

    "budapesta": (47.50, 19.04, "Hungary"),
    "debretin": (47.53, 21.63, "Hungary"),
    "seghedin": (46.25, 20.15, "Hungary"),
    "bekescsaba": (46.68, 21.08, "Hungary"),
    "paks": (46.58, 18.85, "Hungary"),

    "sofia": (42.70, 23.32, "Bulgaria"),
    "varna": (43.21, 27.91, "Bulgaria"),
    "ruse": (43.84, 25.97, "Bulgaria"),
    "kozlodui": (43.78, 23.68, "Bulgaria"),
    "dobrici": (43.57, 27.83, "Bulgaria"),

    "chisinau": (47.01, 28.86, "Moldova"),
    "balti": (47.76, 27.93, "Moldova"),
    "vulcanesti": (45.68, 28.40, "Moldova"),
    "tiraspol": (46.84, 29.64, "Moldova"),
}

RANDOM_SEED = 42
