"""Build a retrospective outage-data quality table, never an ML feature table."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from gridsense import config
from gridsense.data.build_file_library import install_staged
from gridsense.data.build_regional import sha256_file

EVENT_KEY = ["area_code", "instance_code", "version", "asset_code", "segment_start_utc", "segment_end_utc"]
FLAGS = ["missing_available_capacity", "missing_reference", "ambiguous_reference",
         "available_exceeds_installed", "segment_crosses_validity_end", "multiple_publication_times"]


def find_exceptions(outages: pd.DataFrame, production: pd.DataFrame, generation: pd.DataFrame) -> pd.DataFrame:
    """Match retrospective references at segment start and retain flagged segments.

    Reference timestamps and statuses are retained for investigation. Neither the
    matching nor the resulting flags establish what was known at forecast time.
    """
    events = outages.copy().reset_index(drop=True)
    if events.empty or events[EVENT_KEY].isna().any().any() or events.duplicated(EVENT_KEY).any():
        raise ValueError("Outage segment keys must be present and unique")
    events["_row"] = range(len(events))
    matches = []
    for kind, units, identifier, capacity, status in (
        ("PRODUCTION", production, "production_unit_code", "installed_capacity_mw", "status"),
        ("GENERATION", generation, "generation_unit_code", "generation_installed_capacity_mw", "generation_unit_status"),
    ):
        reference = units[[identifier, capacity, status, "valid_from_utc", "valid_to_utc", "updated_at_utc"]].rename(
            columns={identifier: "ref_asset", capacity: "reference_installed_mw", status: "reference_status",
                     "valid_from_utc": "reference_valid_from_utc", "valid_to_utc": "reference_valid_to_utc",
                     "updated_at_utc": "reference_updated_at_utc"}
        )
        joined = events.loc[events.asset_type.eq(kind), ["_row", "asset_code", "segment_start_utc"]].merge(
            reference, left_on="asset_code", right_on="ref_asset", how="left", validate="many_to_many"
        )
        valid = joined.reference_installed_mw.notna() & joined.reference_valid_from_utc.le(joined.segment_start_utc)
        valid &= joined.reference_valid_to_utc.isna() | joined.segment_start_utc.lt(joined.reference_valid_to_utc)
        matches.append(joined.loc[valid].drop(columns=["asset_code", "segment_start_utc", "ref_asset"]))
    candidates = pd.concat(matches, ignore_index=True)
    sizes = candidates.groupby("_row").size()
    unique = candidates.loc[candidates._row.isin(sizes.index[sizes.eq(1)])]
    result = events.merge(unique, how="left", on="_row", validate="one_to_one")
    result["missing_available_capacity"] = result.available_capacity_mw.isna()
    result["missing_reference"] = ~result._row.isin(sizes.index)
    result["ambiguous_reference"] = result._row.isin(sizes.index[sizes.gt(1)])
    result["available_exceeds_installed"] = result.available_capacity_mw.gt(result.reference_installed_mw)
    result["segment_crosses_validity_end"] = (
        result.reference_valid_to_utc.notna() & result.segment_end_utc.gt(result.reference_valid_to_utc)
    )
    result["multiple_publication_times"] = (
        result.groupby(["instance_code", "version"])["published_at_utc"].transform("nunique").gt(1)
    )
    return result.loc[result[FLAGS].any(axis=1)].drop(columns="_row").reset_index(drop=True)


def main() -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("Use GRIDSENSE_DATA=real for outage quality report")
    root = config.PROCESSED_DIR / "entsoe_file_library"
    paths = {
        "outages": root / "outages.parquet",
        "production_units": root / "unit_reference/production_units.parquet",
        "generation_units": root / "unit_reference/generation_units.parquet",
    }
    tables = {name: pd.read_parquet(path) for name, path in paths.items()}
    exceptions = find_exceptions(tables["outages"], tables["production_units"], tables["generation_units"])
    output, report = "outage_quality_exceptions.parquet", "outage_quality_manifest.json"
    with TemporaryDirectory(prefix=".outage-quality-", dir=root) as tmp:
        staged = Path(tmp)
        exceptions.to_parquet(staged / output, index=False)
        manifest = {
            "warning": "Retrospective data-quality investigation only; not an as-of feature dataset.",
            "inputs_sha256": {name: sha256_file(path) for name, path in paths.items()},
            "output_sha256": sha256_file(staged / output),
            "rows": len(exceptions),
            "key": EVENT_KEY,
            "flag_counts": {flag: int(exceptions[flag].sum()) for flag in FLAGS},
        }
        (staged / report).write_text(json.dumps(manifest, indent=2) + "\n")
        install_staged(staged, root, [output, report])
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
