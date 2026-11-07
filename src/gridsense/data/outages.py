"""Unavailability of Romanian generation units (TR 15.1) as known at each issue time.

Parses the File Library monthly extracts into one row per message version and period, then turns them into
hour-average MW offline using only the latest version of each message published by issue time.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.schemas import FEATURE_PREFIX as F

GENERATION_UNITS_FOLDER = "UnavailabilityOfProductionAndGenerationUnits_15.1.A_B_C_D_r3.1"
FUELS = ("nuclear", "hydro", "fossil", "other")
INACTIVE_STATUSES = {"cancelled", "withdrawn", "a09", "a13"}
# Column names vary between export versions; keys are lowercase alphanumerics only.
REQUIRED = {
    "message_id": ("mrid", "messageid", "id"),
    "published_utc": ("updatetime", "updatetimeutc", "publicationtime", "publicationtimeutc"),
    "start_utc": ("startts", "starttsutc", "starttime", "start"),
    "end_utc": ("endts", "endtsutc", "endtime", "end"),
    "area": ("mapcode", "areacode", "biddingzone"),
    "production_type": ("productiontype", "psrtype"),
    "installed_mw": ("installedcapacity", "installedgencapacity", "nominalpower"),
    "available_mw": ("availablecapacity",),
}
OPTIONAL = {
    "unit_name": ("unitname", "generationunitname", "productionunitname"),
    "status": ("status", "docstatus"),
    "unavailability_type": ("type", "unavailabilitytype", "businesstype"),
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _fuel(production_type: str) -> str:
    t = str(production_type).lower()
    if "nuclear" in t or t == "b14":
        return "nuclear"
    if "hydro" in t or t in {"b10", "b11", "b12"}:
        return "hydro"
    if "fossil" in t or t in {"b02", "b03", "b04", "b05", "b06", "b07", "b08"}:
        return "fossil"
    return "other"


def read_export(path: Path) -> pd.DataFrame:
    """Romanian rows of one monthly export, with canonical columns and types."""
    with path.open(encoding="utf-8-sig") as f:
        sep = "\t" if "\t" in f.readline() else ","
    raw = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    by_key = {_key(c): c for c in raw.columns}
    picked = {}
    for name, candidates in {**REQUIRED, **OPTIONAL}.items():
        found = next((by_key[c] for c in candidates if c in by_key), None)
        if found is None and name in REQUIRED:
            raise ValueError(f"{path.name}: no column for {name}; found {list(raw.columns)}")
        if found is not None:
            picked[name] = raw[found].str.strip()
    df = pd.DataFrame(picked)
    df = df[df["area"].isin(["RO", config.BIDDING_ZONE])].copy()

    # The extracts report all timestamps in UTC without an offset.
    for col in ("published_utc", "start_utc", "end_utc"):
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601").astype("datetime64[ns, UTC]")
    for col in ("installed_mw", "available_mw"):
        df[col] = pd.to_numeric(df[col]).astype("float64")
    df["unavailable_mw"] = (df["installed_mw"] - df["available_mw"]).clip(lower=0)
    status = df["status"] if "status" in df else pd.Series("", index=df.index)
    df["active"] = ~status.str.lower().isin(INACTIVE_STATUSES)
    df["fuel"] = df["production_type"].map(_fuel)

    bad = df[["published_utc", "start_utc", "end_utc", "unavailable_mw"]].isna().any(axis=1)
    if bad.any() or (df["end_utc"] <= df["start_utc"]).any():
        raise ValueError(f"{path.name}: missing values or non-positive outage periods")
    return df.reset_index(drop=True)


def load_events(folder: str = GENERATION_UNITS_FOLDER) -> pd.DataFrame:
    paths = sorted((config.RAW_DIR / "entsoe_file_library" / folder).glob("*.csv"))
    if not paths:
        raise ValueError(f"No extracts for {folder}; run gridsense.data.entsoe_files first")
    events = pd.concat([read_export(p) for p in paths], ignore_index=True).drop_duplicates()
    return events.sort_values(["published_utc", "message_id"], ignore_index=True)


def offline_mw_as_of(events: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    """Hour-average MW offline per fuel for each (issue_ts, target_ts_utc) row of `rows`."""
    columns = [f"{F}offline_mw_{fuel}" for fuel in (*FUELS, "total")]
    out = pd.DataFrame(0.0, index=rows.index, columns=columns)
    hour = pd.Timedelta(hours=1).value
    events = events.sort_values("published_utc", ignore_index=True)
    published = pd.DatetimeIndex(events["published_utc"]).asi8

    for issue_ts, group in rows.groupby("issue_ts", sort=False):
        known = events.iloc[: np.searchsorted(published, issue_ts.value, side="right")]
        # All periods of a message's latest version share its publication time.
        latest = known.groupby("message_id")["published_utc"].transform("max")
        known = known[(known["published_utc"] == latest) & known["active"]]
        targets = pd.DatetimeIndex(group["target_ts_utc"]).asi8
        start = pd.DatetimeIndex(known["start_utc"]).asi8
        end = pd.DatetimeIndex(known["end_utc"]).asi8
        in_window = (end > targets.min()) & (start < targets.max() + hour)
        if not in_window.any():
            continue
        start, end = start[in_window, None], end[in_window, None]
        overlap = (np.minimum(end, targets + hour) - np.maximum(start, targets)).clip(0) / hour
        mw = overlap * known["unavailable_mw"].to_numpy()[in_window, None]
        fuel = known["fuel"].to_numpy()[in_window]
        for name in FUELS:
            out.loc[group.index, f"{F}offline_mw_{name}"] = mw[fuel == name].sum(axis=0)
        out.loc[group.index, f"{F}offline_mw_total"] = mw.sum(axis=0)
    return out


def main() -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("Set GRIDSENSE_DATA=real to build outage data")
    events = load_events()
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    events.to_parquet(config.PROCESSED_DIR / "outage_events.parquet", index=False)
    print(
        f"{events['message_id'].nunique():,} messages, {len(events):,} versions/periods, "
        f"published {events['published_utc'].min():%Y-%m-%d}..{events['published_utc'].max():%Y-%m-%d}"
    )
    print(events.groupby("fuel")["message_id"].nunique().to_string())


if __name__ == "__main__":
    main()
