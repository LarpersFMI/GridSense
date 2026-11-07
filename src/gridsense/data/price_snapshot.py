"""Pinned third-party export of ENTSO-E A44, available without API credentials."""

from hashlib import sha256

import pandas as pd
import requests

from gridsense import config
from gridsense.data.entsoe import LOGGER, download, normalize_native

REVISION = "d96677b452e97ebbeec83f9c00939a46e9c21c43"
URL = f"https://huggingface.co/datasets/hsilvosa/entsoe-day-ahead/resolve/{REVISION}"
SHARDS = {
    "train-00008.parquet": "430828f90d531c0a2e312aadaee868f8aa84eb6542501934364aebc8a30c8049",
    "train-00009.parquet": "139838c3e81f3554e109a74f150e04ed751459b9f388dab6f761072111d21e19",
}
SNAPSHOT_END = pd.Timestamp("2026-08-01", tz="UTC")
EUR_START = pd.Timestamp("2021-06-17 22:00", tz="UTC")


def fetch_snapshot_prices(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if start < EUR_START or end > SNAPSHOT_END:
        raise ValueError(
            f"Requested range exceeds this snapshot's Romanian EUR window "
            f"[{EUR_START}, {SNAPSHOT_END}); use --source entsoe for newer data"
        )
    raw = config.RAW_DIR / "entsoe_prices" / "snapshot" / REVISION
    frames = []
    filters = [
        ("eic_code", "==", config.BIDDING_ZONE),
        ("timestamp_utc", ">=", start),
        ("timestamp_utc", "<", end),
    ]
    with requests.Session() as session:
        for name, expected_sha in SHARDS.items():
            path = raw / name
            if not path.is_file():
                LOGGER.info("Downloading ENTSO-E snapshot %s", name)
                download(session, f"{URL}/data/day_ahead_prices/{name}?download=true", path)
            if sha256(path.read_bytes()).hexdigest() != expected_sha:
                raise ValueError(f"Checksum mismatch for {path}; remove it and rerun")
            frames.append(pd.read_parquet(path, filters=filters))
    df = pd.concat(frames, ignore_index=True)
    for column, expected in (("currency", "EUR"), ("unit", "MWH"), ("contract_type", "A01")):
        if not df[column].eq(expected).fillna(False).all():
            raise ValueError(f"Snapshot contains unexpected {column}; expected {expected}")
    df["document_created_at_utc"] = pd.NaT
    columns = {
        "timestamp_utc": "ts_utc",
        "price": "price_eur_mwh",
        "resolution": "resolution",
        "source_file": "source_file",
        "document_id": "document_id",
        "revision_number": "revision_number",
        "document_created_at_utc": "document_created_at_utc",
    }
    return normalize_native(df[list(columns)].rename(columns=columns), "entsoe_snapshot")
