"""Compare historical inventory capacities with retrospective outage references."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from gridsense import config
from gridsense.data.build_file_library import install_staged
from gridsense.data.build_regional import sha256_file


def compare(events: pd.DataFrame, reference: pd.DataFrame, historical: pd.DataFrame,
            code: str, capacity: str, old_capacity: str) -> dict:
    """Count comparable segments without assuming either capacity was available as-of."""
    rows = events.reset_index(drop=True).copy()
    rows["_row"] = range(len(rows))
    matched = rows[["_row", "asset_code", "segment_start_utc"]].merge(
        reference[[code, capacity, "valid_from_utc", "valid_to_utc"]],
        left_on="asset_code", right_on=code, how="left",
    )
    valid = matched.valid_from_utc.le(matched.segment_start_utc) & (
        matched.valid_to_utc.isna() | matched.segment_start_utc.lt(matched.valid_to_utc)
    )
    matched = matched.loc[valid]
    if matched._row.duplicated().any():
        raise ValueError("Ambiguous current reference for an outage segment")
    old = historical[[code, old_capacity]].dropna().drop_duplicates()
    if old[code].duplicated().any():
        raise ValueError("Conflicting historical capacities for an asset")
    matched = matched.merge(old, left_on="asset_code", right_on=code, how="left", suffixes=("", "_old"))
    comparable = matched[capacity].notna() & matched[old_capacity].notna()
    delta = (matched[capacity] - matched[old_capacity]).abs()
    different = comparable & delta.gt(1e-9)
    return {
        "segments": len(rows), "segments_with_current_reference": len(matched),
        "capacity_pairs_compared": int(comparable.sum()),
        "same_capacity_segments": int((comparable & ~different).sum()),
        "different_capacity_segments": int(different.sum()),
        "different_capacity_assets": int(matched.loc[different, "asset_code"].nunique()),
        "maximum_absolute_difference_mw": float(delta[different].max()) if different.any() else 0.0,
    }


def main() -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("Use GRIDSENSE_DATA=real")
    root = config.PROCESSED_DIR / "entsoe_file_library"
    paths = {"outages": root / "outages.parquet",
             "production": root / "unit_reference/production_units.parquet",
             "generation": root / "unit_reference/generation_units.parquet",
             "historical": root / "unit_reference/jrc_2019_units.parquet"}
    tables = {name: pd.read_parquet(path) for name, path in paths.items()}
    results = {}
    for kind, name, code, capacity, old_capacity in (
        ("PRODUCTION", "production", "production_unit_code", "installed_capacity_mw", "production_capacity_mw"),
        ("GENERATION", "generation", "generation_unit_code", "generation_installed_capacity_mw", "generation_capacity_mw"),
    ):
        results[name] = compare(tables["outages"].loc[tables["outages"].asset_type.eq(kind)],
                                tables[name], tables["historical"], code, capacity, old_capacity)
    report = {"warning": "Retrospective comparison only. Neither historical validity nor forecast-time availability is established; not an ML feature.",
              "inputs_sha256": {name: sha256_file(path) for name, path in paths.items()}, "results": results}
    destination = root / "unit_reference"
    with TemporaryDirectory(prefix=".capacity-compare-", dir=destination) as tmp:
        staged = Path(tmp)
        (staged / "jrc_2019_comparison.json").write_text(json.dumps(report, indent=2) + "\n")
        install_staged(staged, destination, ["jrc_2019_comparison.json"])
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
