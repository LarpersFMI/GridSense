"""Normalize Romanian ENTSO-E unit reference snapshots; not an as-of archive."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.data.build_file_library import install_staged
from gridsense.data.build_regional import sha256_file

PRODUCTION = "InstalledGenerationCapacityPerProductionUnit_14.1.B_r3.1.csv"
GENERATION = "ProductionAndGenerationUnits_r3.1.csv"
COMMON = {
    "ValidityPeriodStart(UTC)": "valid_from_utc",
    "ValidityPeriodEnd(UTC)": "valid_to_utc",
    "ProductionUnitCode": "production_unit_code",
    "ProductionUnitName": "production_unit_name",
    "AreaCode": "area_code",
    "AreaMapCode": "country_code",
    "UpdateTime(UTC)": "updated_at_utc",
}
SPECS = {
    "production_units": (
        PRODUCTION,
        {
            **COMMON,
            "Status": "status",
            "ProductionType": "production_type",
            "ProductionUnitLocation": "location",
            "InstalledCapacity[MW]": "installed_capacity_mw",
            "VoltageLevel[kV]": "voltage_kv",
        },
        ["production_unit_code", "valid_from_utc", "valid_to_utc"],
    ),
    "generation_units": (
        GENERATION,
        {
            **COMMON,
            "ProductionUnitStatus": "production_unit_status",
            "ProductionUnitType": "production_unit_type",
            "ProductionUnitLocation": "production_unit_location",
            "ProductionUnitInstalledCapacity[MW]": "production_installed_capacity_mw",
            "ProductionUnitVoltage[kV]": "production_voltage_kv",
            "GenerationUnitCode": "generation_unit_code",
            "GenerationUnitName": "generation_unit_name",
            "GenerationUnitStatus": "generation_unit_status",
            "GenerationUnitType": "generation_unit_type",
            "GenerationUnitLocation": "generation_unit_location",
            "GenerationUnitInstalledCapacity[MW]": "generation_installed_capacity_mw",
        },
        ["production_unit_code", "generation_unit_code", "valid_from_utc", "valid_to_utc"],
    ),
}


def normalize(raw: pd.DataFrame, name: str) -> pd.DataFrame:
    """Keep reference snapshots and their update/validity timestamps without inference."""
    _, columns, key = SPECS[name]
    raw = raw.loc[
        raw["AreaCode"].eq(config.BIDDING_ZONE) & raw["AreaMapCode"].eq("RO"),
        list(columns),
    ].copy()
    if raw.empty:
        raise ValueError(f"{name}: no Romanian records")
    raw = raw.replace(r"^\s*$", pd.NA, regex=True).rename(columns=columns)
    for column in ("valid_from_utc", "valid_to_utc", "updated_at_utc"):
        raw[column] = pd.to_datetime(raw[column], utc=True, format="ISO8601")
    if raw[["valid_from_utc", "updated_at_utc", "production_unit_code"]].isna().any().any():
        raise ValueError(f"{name}: missing mandatory identifier or timestamp")
    if (raw.valid_to_utc.notna() & raw.valid_to_utc.le(raw.valid_from_utc)).any():
        raise ValueError(f"{name}: invalid validity interval")
    for column in raw.columns:
        if column.endswith(("_mw", "_kv")):
            raw[column] = pd.to_numeric(raw[column], errors="raise").astype("float64")
            present = raw[column].dropna()
            if not np.isfinite(present).all() or present.lt(0).any():
                raise ValueError(f"{name}: invalid {column}")
    if raw.duplicated(key).any():
        raise ValueError(f"{name}: duplicate reference keys")
    return raw.sort_values(key, na_position="last", ignore_index=True)


def build(archive: Path, destination: Path, *, replace_existing: bool = False) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as source, TemporaryDirectory(prefix=".unit-ref-", dir=destination) as tmp:
        staged = Path(tmp)
        reports = {}
        for name, (filename, _, key) in SPECS.items():
            payload = source.read(filename)
            with source.open(filename) as stream:
                raw = pd.read_csv(stream, sep="\t", dtype="string", keep_default_na=False)
            frame = normalize(raw, name)
            output = staged / f"{name}.parquet"
            frame.to_parquet(output, index=False)
            reports[name] = {
                "source_file": filename,
                "source_sha256": hashlib.sha256(payload).hexdigest(),
                "rows": len(frame),
                "key": key,
                "duplicate_keys": 0,
                "updated_at_utc_min": frame.updated_at_utc.min().isoformat(),
                "updated_at_utc_max": frame.updated_at_utc.max().isoformat(),
                "output_sha256": sha256_file(output),
            }
        manifest = {
            "source": "ENTSO-E Transparency Platform File Library",
            "source_archive_sha256": sha256_file(archive),
            "warning": "Snapshot reference only; update timestamps do not establish earlier availability.",
            "tables": reports,
        }
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        install_staged(
            staged,
            destination,
            [*(f"{name}.parquet" for name in SPECS), "manifest.json"],
            replace_existing=replace_existing,
        )
    print(f"Wrote Romanian unit reference tables and manifest to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=config.RAW_DIR / "entsoe_file_library/unit_capacity_reference.zip"
    )
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real to build real unit reference data")
    build(args.input, config.PROCESSED_DIR / "entsoe_file_library/unit_reference", replace_existing=args.replace_existing)


if __name__ == "__main__":
    main()
