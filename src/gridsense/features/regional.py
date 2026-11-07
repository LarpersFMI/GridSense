"""Validated opt-in ML join for the existing regional market Parquet handoff.

No source columns or shared table schemas are changed. The producer supplies
issue-relative price/load lags; original publication/vintage limitations still apply.
"""

import hashlib
import json

import numpy as np
import pandas as pd

from gridsense import config

JOIN_KEYS = ["issue_ts", "target_ts_utc", "horizon_days"]
REGIONAL_PRICE_COLUMNS = tuple(
    f"f_price_{country}_{suffix}"
    for suffix in ("same_hour_d", "same_hour_d_minus_6")
    for country in ("hu", "bg")
)
REGIONAL_SPREAD_COLUMNS = tuple(
    f"f_price_spread_ro_{country}_{suffix}"
    for suffix in ("d", "d_minus_6") for country in ("hu", "bg")
)
REGIONAL_LOAD_COLUMNS = tuple(f"f_load_{country}_same_hour_d_minus_1" for country in ("ro", "hu", "bg"))
REGIONAL_COLUMNS = tuple(sorted((*REGIONAL_PRICE_COLUMNS, *REGIONAL_SPREAD_COLUMNS, *REGIONAL_LOAD_COLUMNS)))


def _keys(table: pd.DataFrame, name: str) -> pd.DataFrame:
    missing = set(JOIN_KEYS) - set(table.columns)
    if missing:
        raise ValueError(f"{name}: missing forecast keys {sorted(missing)}")
    keys = table[JOIN_KEYS].copy()
    for column in ("issue_ts", "target_ts_utc"):
        ts = keys[column]
        if not isinstance(ts.dtype, pd.DatetimeTZDtype) or ts.isna().any():
            raise ValueError(f"{name}.{column} must contain valid timezone-aware UTC hours")
        keys[column] = ts.dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
        if not keys[column].eq(keys[column].dt.floor("h")).all():
            raise ValueError(f"{name}.{column} must be aligned to UTC hours")
    horizon = keys["horizon_days"]
    if not horizon.isin(config.HORIZONS_DAYS).all():
        raise ValueError(f"{name}: invalid forecast horizon")
    keys["horizon_days"] = horizon.astype("int64")
    issue = keys["issue_ts"].dt.tz_convert(config.LOCAL_TZ)
    target = keys["target_ts_utc"].dt.tz_convert(config.LOCAL_TZ)
    days = target.dt.tz_localize(None).dt.normalize() - issue.dt.tz_localize(None).dt.normalize()
    if not issue.dt.hour.eq(config.ISSUE_HOUR).all() or not days.eq(
        pd.to_timedelta(keys["horizon_days"], unit="D")
    ).all():
        raise ValueError(f"{name}: forecast keys do not match the configured local issue clock/horizon")
    if keys.duplicated().any():
        raise ValueError(f"{name}: forecast keys must be unique")
    return keys


def validate_regional_table(regional: pd.DataFrame) -> None:
    _keys(regional, "regional")
    features = {c for c in regional if c.startswith("f_")}
    if features != set(REGIONAL_COLUMNS):
        raise ValueError("Regional handoff must contain exactly the 11 documented lag/spread features")
    for column in REGIONAL_COLUMNS:
        values = regional[column]
        if not pd.api.types.is_numeric_dtype(values):
            raise ValueError(f"Regional feature {column} must be numeric")
        if np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).any():
            raise ValueError(f"Regional feature {column} contains infinite values")
        if column in REGIONAL_LOAD_COLUMNS and values.dropna().lt(0).any():
            raise ValueError(f"Regional load {column} must be nonnegative")


def read_regional_table() -> tuple[pd.DataFrame, dict]:
    """Read the free-form handoff and validate it against its tracked provenance manifest."""
    path = config.PROCESSED_DIR / "regional_market_features.parquet"
    manifest_path = config.PROCESSED_DIR / "regional_market_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    info = manifest["outputs"][path.name]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != info["sha256"]:
        raise ValueError("Regional market features do not match the manifest checksum")
    table = pd.read_parquet(path)
    if len(table) != info["rows"]:
        raise ValueError("Regional market row count does not match the manifest")
    validate_regional_table(table)
    return table, {"sha256": digest, "manifest": manifest}


def join_regional_features(
    training: pd.DataFrame, regional: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    """One-to-one left join; preserve every forecast row/index, label, and original feature."""
    left_keys = _keys(training, "training")
    validate_regional_table(regional)
    if overlap := set(REGIONAL_COLUMNS) & set(training.columns):
        raise ValueError(f"Regional features already exist: {sorted(overlap)}")
    left = training.copy()
    left[JOIN_KEYS] = left_keys
    right = _keys(regional, "regional").join(regional[list(REGIONAL_COLUMNS)])
    merged = left.merge(right, on=JOIN_KEYS, how="left", validate="one_to_one",
                        sort=False, indicator="_regional_match")
    missing = int(merged["_regional_match"].eq("left_only").sum())
    merged = merged.drop(columns="_regional_match").set_axis(training.index)
    # Restore original key dtypes as well as the index (pandas merge may normalize units).
    merged[JOIN_KEYS] = training[JOIN_KEYS]
    if not merged[training.columns].equals(training):
        raise ValueError("Regional join unexpectedly changed original forecast rows")
    incomplete = merged[list(REGIONAL_COLUMNS)].isna().any(axis=1)
    quality = merged.get("data_quality", pd.Series("ok", index=merged.index)).astype("string")
    merged["data_quality"] = quality.where(
        ~incomplete, quality.where(quality.ne("ok"), "").str.strip(";")
        .map(lambda q: f"{q};missing_regional" if q else "missing_regional")
    )
    return merged, missing