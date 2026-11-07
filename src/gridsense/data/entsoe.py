"""Romanian day-ahead prices from the ENTSO-E Transparency Platform (A44)."""

import logging
import os
import tempfile
import time
from itertools import pairwise
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from gridsense import config
from gridsense.schemas import PRICES_HOURLY

API_URL = "https://web-api.tp.entsoe.eu/api"
# The SDAC delivery day starts at midnight CET/CEST (01:00 in Bucharest).
QUARTER_HOUR_START = pd.Timestamp("2025-10-01", tz="Europe/Brussels").tz_convert("UTC")
RESOLUTIONS = {"PT60M": pd.Timedelta(hours=1), "PT15M": pd.Timedelta(minutes=15)}
LOGGER = logging.getLogger(__name__)


def utc_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if pd.isna(ts) or ts.tzinfo is None:
        raise ValueError(f"Expected a timezone-aware timestamp, got {value!r}")
    return ts.tz_convert("UTC").as_unit("ns")


def download(
    session: requests.Session, url: str, path: Path, *, params: dict | None = None
) -> None:
    """Cache the response bytes, publishing the file only after a complete transfer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        temporary = None
        try:
            with session.get(url, params=params, timeout=(10, 60), stream=True) as response:
                status = response.status_code
                if status == 200:
                    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                        temporary = Path(output.name)
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                    temporary.replace(path)
                    return
                problem = f"HTTP {status}"
                if status != 429 and not 500 <= status < 600:
                    break
        except requests.RequestException as exc:
            # Request exceptions may include the query URL and security token.
            problem = type(exc).__name__
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        if attempt < 2:
            time.sleep(2**attempt)
    raise ValueError(f"Download failed for {path.name}: {problem}")


def _parse_period(period: ET.Element, curve: str, metadata: dict) -> list[dict]:
    start = utc_timestamp(period.findtext("{*}timeInterval/{*}start"))
    end = utc_timestamp(period.findtext("{*}timeInterval/{*}end"))
    resolution = period.findtext("{*}resolution")
    if resolution not in RESOLUTIONS:
        raise ValueError(f"Unsupported ENTSO-E price resolution {resolution!r}")
    step = RESOLUTIONS[resolution]
    size, remainder = divmod(end - start, step)
    if size <= 0 or remainder:
        raise ValueError("Invalid ENTSO-E period boundaries")

    points = {}
    for point in period.findall("{*}Point"):
        position = int(point.findtext("{*}position", "0"))
        if position in points or not 1 <= position <= size:
            raise ValueError(f"Duplicate or invalid ENTSO-E point position {position}")
        points[position] = float(point.findtext("{*}price.amount", "nan"))
    if not points:
        raise ValueError("ENTSO-E returned a period without prices")
    if curve == "A03" and 1 not in points:
        raise ValueError("ENTSO-E A03 period has no initial block")

    rows = []
    positions = sorted(points)
    for pos, next_pos in zip(positions, positions[1:] + [size + 1]):
        # A03 encodes the same value for an entire variable-length block.
        stop = next_pos if curve == "A03" else pos + 1
        rows.extend(
            dict(
                metadata,
                ts_utc=start + (i - 1) * step,
                resolution=resolution,
                price_eur_mwh=points[pos],
            )
            for i in range(pos, stop)
        )
    return rows


def parse_price_xml(payload: bytes, source_file: str) -> pd.DataFrame:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise ValueError(f"{source_file}: expected an ENTSO-E XML price document") from None
    if root.findtext("{*}type") != "A44":
        raise ValueError(f"{source_file}: ENTSO-E did not return an A44 price document")

    created = root.findtext("{*}createdDateTime")
    rows = []
    for series in root.findall("{*}TimeSeries"):
        if series.findtext("{*}contract_MarketAgreement.type") != "A01":
            raise ValueError(f"{source_file}: expected a day-ahead (A01) price series")
        if any(
            series.findtext(f"{{*}}{direction}_Domain.mRID") != config.BIDDING_ZONE
            for direction in ("in", "out")
        ):
            raise ValueError(f"{source_file}: unexpected price bidding zone")
        currency = series.findtext("{*}currency_Unit.name")
        unit = series.findtext("{*}price_Measure_Unit.name")
        if (currency, unit) != ("EUR", "MWH"):
            raise ValueError(f"{source_file}: expected prices in EUR/MWh")
        curve = series.findtext("{*}curveType", "A01")
        if curve not in ("A01", "A03"):
            raise ValueError(f"{source_file}: unsupported ENTSO-E curve type {curve!r}")
        metadata = {
            "source_file": source_file,
            "document_id": root.findtext("{*}mRID"),
            "revision_number": root.findtext("{*}revisionNumber"),
            "document_created_at_utc": utc_timestamp(created) if created else pd.NaT,
        }
        periods = series.findall("{*}Period")
        if not periods:
            raise ValueError(f"{source_file}: ENTSO-E series contains no periods")
        for period in periods:
            rows.extend(_parse_period(period, curve, metadata))
    if not rows:
        raise ValueError(f"{source_file}: ENTSO-E returned no price series")
    return pd.DataFrame(rows)


def fetch_day_ahead_prices(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Fetch native market intervals from the official API for [start, end)."""
    start, end = utc_timestamp(start), utc_timestamp(end)
    if not start < end or any(ts != ts.floor("h") for ts in (start, end)):
        raise ValueError("Expected an increasing range on whole UTC hours")

    load_dotenv(config.ROOT / ".env")
    token = os.getenv("ENTSOE_API_TOKEN", "").strip()
    month_starts = pd.date_range(start.normalize(), end, freq="MS")
    boundaries = [start, *month_starts[(month_starts > start) & (month_starts < end)], end]
    frames = []
    raw = config.RAW_DIR / "entsoe_prices" / "api"
    with requests.Session() as session:
        for left, right in pairwise(boundaries):
            label = f"{left:%Y%m%dT%H%MZ}_{right:%Y%m%dT%H%MZ}"
            path = raw / f"{label}.xml"
            if not path.is_file():
                if not token:
                    raise ValueError("Set ENTSOE_API_TOKEN in the environment or the repo's .env")
                LOGGER.info("Downloading ENTSO-E A44 %s", label)
                download(
                    session,
                    API_URL,
                    path,
                    params={
                        "securityToken": token,
                        "documentType": "A44",
                        "contract_MarketAgreement.type": "A01",
                        "in_Domain": config.BIDDING_ZONE,
                        "out_Domain": config.BIDDING_ZONE,
                        "periodStart": left.strftime("%Y%m%d%H%M"),
                        "periodEnd": right.strftime("%Y%m%d%H%M"),
                    },
                )
            df = parse_price_xml(path.read_bytes(), path.name)
            # The API can include complete delivery days outside the query's UTC bounds.
            frames.append(df.loc[df["ts_utc"].between(left, right, inclusive="left")])

    return normalize_native(pd.concat(frames, ignore_index=True), "entsoe_api")


def normalize_native(df: pd.DataFrame, source: str) -> pd.DataFrame:
    if df.empty:
        raise ValueError("No Romanian price observations in the requested range")
    df = df.copy()
    if not isinstance(df["ts_utc"].dtype, pd.DatetimeTZDtype):
        raise TypeError("Native timestamps must be timezone-aware")
    df["ts_utc"] = df["ts_utc"].dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
    df["price_eur_mwh"] = pd.to_numeric(df["price_eur_mwh"]).astype("float64")
    df["interval_end_utc"] = df["ts_utc"] + df["resolution"].map(RESOLUTIONS)
    df["source"] = source
    df["market"] = "day_ahead"
    df["bidding_zone"] = config.BIDDING_ZONE
    df["document_created_at_utc"] = pd.to_datetime(df["document_created_at_utc"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    df["revision_number"] = df["revision_number"].astype("Int64")
    for column in ("resolution", "source", "market", "bidding_zone", "document_id", "source_file"):
        df[column] = df[column].astype("string")
    df = df.sort_values("ts_utc", ignore_index=True)
    _validate_intervals(df)
    return df


def _validate_intervals(df: pd.DataFrame) -> None:
    ts = df["ts_utc"]
    if str(ts.dtype) != "datetime64[ns, UTC]" or ts.isna().any():
        raise ValueError("Expected valid datetime64[ns, UTC] delivery timestamps")
    if ts.duplicated().any():
        raise ValueError(f"Duplicate market interval at {ts[ts.duplicated()].iloc[0]}")
    if not ts.is_monotonic_increasing:
        raise ValueError("Price timestamps must be chronological")
    if not np.isfinite(df["price_eur_mwh"].astype(float)).all():
        raise ValueError("Prices must be finite numeric values in EUR/MWh")
    expected = np.where(ts < QUARTER_HOUR_START, "PT60M", "PT15M")
    bad_resolution = df["resolution"].isna() | df["resolution"].ne(expected)
    if bad_resolution.any():
        raise ValueError(f"Unexpected market resolution at {ts[bad_resolution].iloc[0]}")
    if ((ts != ts.dt.floor("15min")) | ((ts < QUARTER_HOUR_START) & (ts.dt.minute != 0))).any():
        raise ValueError("Market timestamps are not aligned to their delivery intervals")


def to_hourly(prices_15min: pd.DataFrame) -> pd.DataFrame:
    """Aggregate complete UTC hours only, keeping mean, minimum and maximum in EUR/MWh."""
    _validate_intervals(prices_15min)
    prices = prices_15min.groupby(prices_15min["ts_utc"].dt.floor("h"))["price_eur_mwh"]
    hourly = prices.agg(price_mean="mean", price_min="min", price_max="max")
    expected_counts = np.where(hourly.index < QUARTER_HOUR_START, 1, 4)
    return hourly.loc[prices.size() == expected_counts].reset_index().astype(PRICES_HOURLY)


def fetch_load(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raise NotImplementedError


def fetch_generation(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raise NotImplementedError
