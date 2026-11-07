"""Build a conservative, issue-time-safe Romanian week-ahead forecast handoff."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.data.build_file_library import install_staged
from gridsense.data.build_regional import sha256_file

KEYS = ["issue_ts", "target_ts_utc", "horizon_days"]
VALUES = ["load_fc_min_mw", "load_fc_max_mw", "load_fc_updated_at_utc"]


def build_asof(keys: pd.DataFrame, vintages: pd.DataFrame) -> pd.DataFrame:
    """Select the latest recorded update available at issue time for each target day.

    Missing historical vintages remain null; an update timestamp is only evidence of
    availability by that time, not evidence of when a previous value was available.
    """
    keys = keys[KEYS].copy()
    if keys.isna().any().any() or keys.duplicated(KEYS).any():
        raise ValueError("Forecast keys must be non-null and unique")
    for column in ("issue_ts", "target_ts_utc"):
        if not isinstance(keys[column].dtype, pd.DatetimeTZDtype):
            raise TypeError(f"{column} must be timezone-aware")
        keys[column] = keys[column].dt.tz_convert("UTC")
    issue_local = keys.issue_ts.dt.tz_convert(config.LOCAL_TZ)
    target_local = keys.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
    issue_day = issue_local.dt.tz_localize(None).dt.normalize()
    target_day = target_local.dt.tz_localize(None).dt.normalize()
    if not (
        keys.horizon_days.isin(config.HORIZONS_DAYS)
        & target_day.sub(issue_day).dt.days.eq(keys.horizon_days)
        & issue_local.dt.hour.eq(config.ISSUE_HOUR)
        & issue_local.dt.minute.eq(0)
        & issue_local.dt.second.eq(0)
    ).all():
        raise ValueError("Forecast keys do not match the configured issue clock and horizons")
    keys["target_date"] = target_day
    keys["_order"] = range(len(keys))

    source = vintages.loc[
        vintages.area_code.eq(config.BIDDING_ZONE)
        & vintages.contract_type.eq("Week-ahead")
        & vintages.resolution.eq("P1D"),
        ["ts_utc", "updated_at_utc", "min_load_mw", "max_load_mw"],
    ].copy()
    if source.empty:
        raise ValueError("No Romanian daily week-ahead forecast records")
    for column in ("ts_utc", "updated_at_utc"):
        if not isinstance(source[column].dtype, pd.DatetimeTZDtype) or source[column].isna().any():
            raise ValueError(f"{column} must contain timezone-aware timestamps")
        source[column] = source[column].dt.tz_convert("UTC")
    for column in ("min_load_mw", "max_load_mw"):
        source[column] = pd.to_numeric(source[column], errors="raise")
    if (
        source[["min_load_mw", "max_load_mw"]].isna().any().any()
        or not np.isfinite(source[["min_load_mw", "max_load_mw"]].to_numpy()).all()
        or source["min_load_mw"].lt(0).any()
        or source["min_load_mw"].gt(source["max_load_mw"]).any()
    ):
        raise ValueError("Invalid week-ahead min/max values")
    source["target_date"] = (
        source.ts_utc.dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    )
    source = source.drop(columns="ts_utc").drop_duplicates()
    if source.duplicated(["target_date", "updated_at_utc"]).any():
        raise ValueError("Conflicting forecasts for the same target date and update time")
    source = source.rename(
        columns={
            "updated_at_utc": "load_fc_updated_at_utc",
            "min_load_mw": "load_fc_min_mw",
            "max_load_mw": "load_fc_max_mw",
        }
    )
    result = pd.merge_asof(
        keys.sort_values("issue_ts"),
        source.sort_values("load_fc_updated_at_utc"),
        left_on="issue_ts",
        right_on="load_fc_updated_at_utc",
        by="target_date",
        direction="backward",
        allow_exact_matches=True,
    )
    return result.sort_values("_order", ignore_index=True)[KEYS + VALUES]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace-existing", action="store_true", help="Replace reviewed, differing outputs"
    )
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        raise SystemExit("Set GRIDSENSE_DATA=real to build this handoff")
    keys_path = config.PROCESSED_DIR / "training_table.parquet"
    source_path = config.PROCESSED_DIR / "entsoe_file_library/week_ahead_load.parquet"
    keys = pd.read_parquet(keys_path, columns=KEYS)
    source = pd.read_parquet(source_path)
    result = build_asof(keys, source)
    output = "load_fc_week_ahead_asof.parquet"
    report = "load_fc_week_ahead_asof_manifest.json"
    with TemporaryDirectory(prefix=".week-ahead-asof-", dir=config.PROCESSED_DIR) as tmp:
        staged = Path(tmp)
        result.to_parquet(staged / output, index=False)
        manifest = {
            "inputs_sha256": {
                "training_table.parquet": sha256_file(keys_path),
                "entsoe_file_library/week_ahead_load.parquet": sha256_file(source_path),
            },
            "output_sha256": sha256_file(staged / output),
            "rows": len(result),
            "rows_with_forecast": int(result.load_fc_min_mw.notna().sum()),
            "join_keys": KEYS,
            "selection": "latest recorded update at or before issue for local target date",
        }
        (staged / report).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        install_staged(staged, config.PROCESSED_DIR, [output, report], replace_existing=args.replace_existing)
    print(f"{config.PROCESSED_DIR / output}: {len(result):,} rows; {result.load_fc_min_mw.notna().sum():,} available")


if __name__ == "__main__":
    main()
