"""Describe outage-to-unit reference matching without constructing model features."""

import json

import pandas as pd

from gridsense import config


def audit(outages: pd.DataFrame, production: pd.DataFrame, generation: pd.DataFrame) -> dict:
    result = {}
    for kind, units, identifier, capacity in (
        ("PRODUCTION", production, "production_unit_code", "installed_capacity_mw"),
        ("GENERATION", generation, "generation_unit_code", "generation_installed_capacity_mw"),
    ):
        events = outages.loc[outages.asset_type.eq(kind)].reset_index(drop=True).copy()
        events["_row"] = range(len(events))
        relevant = units[[identifier, "valid_from_utc", "valid_to_utc", "updated_at_utc", capacity]]
        joined = events[
            [
                "_row", "asset_code", "segment_start_utc", "segment_end_utc",
                "published_at_utc", "available_capacity_mw",
            ]
        ].merge(relevant, left_on="asset_code", right_on=identifier, how="left", validate="many_to_many")
        matches = joined.loc[
            joined[capacity].notna()
            & joined.valid_from_utc.le(joined.segment_start_utc)
            & (joined.valid_to_utc.isna() | joined.segment_start_utc.lt(joined.valid_to_utc))
        ]
        counts = matches.groupby("_row").size()
        result[kind] = {
            "outage_segments": len(events),
            "with_one_valid_capacity_match": int(counts.eq(1).sum()),
            "with_multiple_valid_capacity_matches": int(counts.gt(1).sum()),
            "with_no_valid_capacity_match": len(events) - len(counts),
            "with_capacity_updated_by_outage_publication": int(
                matches.loc[matches.updated_at_utc.le(matches.published_at_utc), "_row"].nunique()
            ),
            "missing_available_capacity": int(events.available_capacity_mw.isna().sum()),
            "available_exceeds_matched_installed_capacity": int(
                matches.loc[matches.available_capacity_mw.gt(matches[capacity]), "_row"].nunique()
            ),
            "segment_extends_past_reference_validity": int(
                matches.loc[
                    matches.valid_to_utc.notna() & matches.segment_end_utc.gt(matches.valid_to_utc),
                    "_row",
                ].nunique()
            ),
        }
    result["other_asset_type_segments"] = int(
        (~outages.asset_type.isin(["PRODUCTION", "GENERATION"])).sum()
    )
    return result


def main() -> None:
    root = config.PROCESSED_DIR / "entsoe_file_library"
    outages = pd.read_parquet(root / "outages.parquet")
    production = pd.read_parquet(root / "unit_reference/production_units.parquet")
    generation = pd.read_parquet(root / "unit_reference/generation_units.parquet")
    print(json.dumps(audit(outages, production, generation), indent=2))


if __name__ == "__main__":
    main()
