"""Shared weather points for Romania, keyed by the IDs used in weather_fc.location."""

from gridsense.config import WEATHER_POINTS

# Order follows resident population in the 2021 Romanian census.
# Values are WGS84 (latitude, longitude). The four MVP points use the existing config.
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
