"""Per-prediction explanations. Owner: SHAP top_features (ML-C), similar days (ML-P)."""

import re

import lightgbm as lgb
import numpy as np
import pandas as pd

from gridsense.schemas import FEATURE_PREFIX

Models = lgb.LGBMClassifier | list[lgb.LGBMClassifier]


def shap_values(models: Models, X: pd.DataFrame) -> pd.DataFrame:
    """SHAP contribution of every feature to every row, in log-odds.

    Uses LightGBM's built-in TreeSHAP (exact for tree models). For one model, per row,
    base value + sum of contributions = the model's raw score (log-odds of the event).
    For a list (the classifier's chain, see LowPriceClassifier.explain_models), contributions
    are summed: p_cheap = p_near_zero * P(cheap | near_zero), so log p_cheap is the sum of the
    two log-probabilities, which log-odds approximate well for the small probabilities involved.
    """
    models = models if isinstance(models, list) else [models]
    contrib = sum(m.booster_.predict(X, pred_contrib=True)[:, :-1] for m in models)
    return pd.DataFrame(contrib, index=X.index, columns=X.columns)


def top_features(models: Models, X: pd.DataFrame, n: int = 3) -> pd.Series:
    """Top-n SHAP contributions per row, as a short string for the agent.

    E.g. "ghi_mean:+1.20; is_weekend:+0.45; cloud_mean:-0.30", largest effect first. "+" pushes
    the prediction toward a low price, "-" away from it. Values are log-odds, so compare them
    with each other rather than reading them as probabilities.
    """
    contrib = shap_values(models, X).to_numpy()
    names = np.array([c.removeprefix(FEATURE_PREFIX) for c in X.columns])
    n = min(n, contrib.shape[1])
    order = np.argsort(-np.abs(contrib), axis=1, kind="stable")[:, :n]
    values = np.take_along_axis(contrib, order, axis=1)
    text = [
        "; ".join(f"{name}:{v:+.2f}" for name, v in zip(names[o], vals, strict=True))
        for o, vals in zip(order, values, strict=True)
    ]
    return pd.Series(text, index=X.index, dtype="string")


# --- Readable explanations (ML-C): top_features -> top_features_text, for the agent and the UI. ---

CITY_NAMES = {
    "bucuresti": "Bucharest",
    "constanta": "Constanța",
    "craiova": "Craiova",
    "timisoara": "Timișoara",
    "iasi": "Iași",
    "cluj_napoca": "Cluj-Napoca",
}

# (regex on the feature name without "f_", phrase). First match wins; {city} is the location group.
# Phrases name the factor, not its value: SHAP gives the push direction, not "high" or "low".
FEATURE_PHRASES: tuple[tuple[str, str], ...] = (
    (r"^ghi_mean$", "sunshine forecast"),
    (r"^ghi_(?P<city>.+)$", "sunshine forecast in {city}"),
    (r"^cloud_mean$", "cloud forecast"),
    (r"^cloud_(?P<city>.+)$", "cloud forecast in {city}"),
    (r"^wind100_mean$", "wind forecast"),
    (r"^wind100_(?P<city>.+)$", "wind forecast in {city}"),
    (r"^temp_mean$", "temperature forecast"),
    (r"^temp_(?P<city>.+)$", "temperature forecast in {city}"),
    (r"^(humidity|precip|pressure|wind10|winddir_sin|winddir_cos)_", "weather forecast"),
    (r"^(doy_(sin|cos)_\d+|month)$", "time of year"),
    (r"^hour$", "hour of day"),
    (r"^weekday$", "day of the week"),
    (r"^is_weekend$", "weekend"),
    (r"^is_holiday$", "public holiday"),
    (r"^is_bridge_day$", "bridge day between holidays"),
    (r"^is_dst$", "summer time"),
    (r"^horizon_days$", "how many days ahead"),
    (r"^price_same_hour_target_m7$", "price at this hour a week earlier"),
    (r"^price_same_hour_d$", "today's price at this hour"),
    (r"^price_same_hour_dm1$", "yesterday's price at this hour"),
    (r"^price_same_hour_(mean|min|max)_7d$", "prices at this hour over the past week"),
    (r"^d_(mean|min|midday_min|evening_max)$", "today's prices"),
    (r"^mean_30d$", "prices over the past month"),
    (r"^midday_min_(7d|30d)$", "recent midday prices"),
    (r"^neg_hours_(7d|30d)$", "recent negative-price hours"),
    (r"^load_mean_dm1$", "yesterday's electricity demand"),
    (r"^load_fc_", "forecast electricity demand"),
    (r"^solar_max_dm1$", "yesterday's solar output"),
    (r"^wind_mean_dm1$", "yesterday's wind output"),
    (r"^feng_solar_potential", "height of the sun"),
    (r"^feng_solar_cloud_proxy", "sunshine forecast"),
    (r"^feng_heating_degree", "heating demand (cold weather)"),
    (r"^feng_cooling_degree", "cooling demand (hot weather)"),
    (r"^feng_(air_density|wind10_power|wind10_u|wind10_v)", "wind forecast"),
    (r"^feng_hour_", "hour of day"),
    (r"^feng_weekday_", "day of the week"),
    (r"^feng_price_recent_", "this morning's prices"),
    (r"^feng_missing_weather$", "missing weather data"),
    (r"^wgrid_", "regional weather forecast"),
    (r"(^|_)(hu|bg)(_|$)", "neighbouring markets"),
)
_COMPILED = tuple((re.compile(pattern), phrase) for pattern, phrase in FEATURE_PHRASES)


def feature_phrase(name: str) -> str:
    """Plain-language name of a feature (with or without the f_ prefix)."""
    name = name.removeprefix(FEATURE_PREFIX)
    for pattern, phrase in _COMPILED:
        match = pattern.search(name)
        if match:
            city = match.groupdict().get("city")
            city = CITY_NAMES.get(city, city.replace("_", " ").title()) if city else ""
            return phrase.format(city=city)
    return name.replace("_", " ")


def describe_top_features(top: pd.Series) -> pd.Series:
    """top_features strings -> one sentence each, e.g.
    "Pointing to a low price: sunshine forecast, weekend. Against: hour of day."

    Same order as top_features (largest effect first); features with the same phrase are merged.
    """

    def one(text: str) -> str:
        toward, against = [], []
        for item in filter(None, (part.strip() for part in str(text).split(";"))):
            name, _, value = item.rpartition(":")
            phrase = feature_phrase(name)
            side = toward if float(value) > 0 else against
            if phrase not in toward and phrase not in against:
                side.append(phrase)
        parts = []
        if toward:
            parts.append("Pointing to a low price: " + ", ".join(toward) + ".")
        if against:
            parts.append("Against: " + ", ".join(against) + ".")
        return " ".join(parts)

    return top.fillna("").map(one).astype("string")
