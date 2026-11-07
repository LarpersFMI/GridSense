"""Prepare a historical JRC reference inventory for outage data investigation."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.data.build_file_library import install_staged
from gridsense.data.build_regional import sha256_file

# The mirror's initial v1.0 commit dates from 2021; equivalence to the official
# archive has not been independently verified.
MIRROR_COMMIT = "c078cfaac011882a99f1606eb7deb0f72e614e93"
FULL_SOURCE_BLOB_SHA1 = "0662c9fad5ee4a670e5027988d3c87d04b57faff"
SOURCE_URL = f"https://github.com/enermaps/JRC-PPDB-OPEN/blob/{MIRROR_COMMIT}/JRC_OPEN_UNITS.csv"
COLS = {
    "eic_p": "production_unit_code", "eic_g": "generation_unit_code",
    "name_p": "production_unit_name", "name_g": "generation_unit_name",
    "capacity_p": "production_capacity_mw", "capacity_g": "generation_capacity_mw",
    "type_g": "generation_type", "country": "country", "status_g": "generation_status",
    "year_commissioned": "year_commissioned", "year_decommissioned": "year_decommissioned",
}


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep identifiers and recorded capacities without inventing validity periods."""
    frame = raw.loc[raw.country.eq("Romania"), list(COLS)].copy().rename(columns=COLS)
    frame = frame.replace(r"^\s*$", pd.NA, regex=True)
    if frame.empty or frame.production_unit_code.isna().any():
        raise ValueError("No Romanian units or missing production-unit codes")
    if frame.duplicated(["production_unit_code", "generation_unit_code"]).any():
        raise ValueError("Duplicate historical unit keys")
    for col in ("production_capacity_mw", "generation_capacity_mw"):
        frame[col] = pd.to_numeric(frame[col], errors="raise").astype("float64")
        present = frame[col].dropna()
        if not np.isfinite(present).all() or present.lt(0).any():
            raise ValueError(f"Invalid {col}")
    return frame.sort_values(["production_unit_code", "generation_unit_code"], na_position="last", ignore_index=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=config.RAW_DIR / "jrc_2019_romania_units_original.csv")
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real")
    raw = pd.read_csv(args.input, dtype="string", keep_default_na=False)
    frame = normalize(raw)
    output, report = "jrc_2019_units.parquet", "jrc_2019_manifest.json"
    destination = config.PROCESSED_DIR / "entsoe_file_library/unit_reference"
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".jrc-units-", dir=destination) as tmp:
        staged = Path(tmp)
        frame.to_parquet(staged / output, index=False)
        manifest = {
            "source": "JRC-PPDB-OPEN v1.0; Romanian rows from the mirror's initial commit; official archive equivalence unverified",
            "source_url": SOURCE_URL,
            "official_dataset": "https://data.jrc.ec.europa.eu/dataset/9810feeb-f062-49cd-8e76-8d8cfd488a05",
            "official_dataset_version": "1.0, published 2019-12-13",
            "mirror_commit": MIRROR_COMMIT,
            "mirror_commit_author_time_utc": "2021-03-16T15:37:37Z",
            "mirror_full_file_git_blob_sha1": FULL_SOURCE_BLOB_SHA1,
            "romanian_input_sha256": sha256_file(args.input),
            "output_sha256": sha256_file(staged / output),
            "rows": len(frame),
            "key": ["production_unit_code", "generation_unit_code"],
            "warning": "Retrospective reference only; publication timing and 2023-2026 validity require independent verification.",
            "license": "CC BY 4.0; European Commission, Joint Research Centre, JRC-PPDB-OPEN v1.0",
        }
        (staged / report).write_text(json.dumps(manifest, indent=2) + "\n")
        install_staged(staged, destination, [output, report], replace_existing=args.replace_existing)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
