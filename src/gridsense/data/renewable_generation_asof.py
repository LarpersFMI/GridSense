"""Prepare conservative D-1 actual renewable-generation inputs for ML."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from gridsense import config
from gridsense.data.build_file_library import complete_hours, install_staged
from gridsense.data.build_regional import sha256_file
from gridsense.splits import assign_split

KEYS = ["issue_ts", "target_ts_utc", "horizon_days"]
FUELS = {"Solar": "solar", "Wind Onshore": "wind"}


def build_handoff(keys: pd.DataFrame, generation: pd.DataFrame) -> pd.DataFrame:
    """Use a full preceding local day only when every hourly value is updated by issue.

    The extract has latest recorded values, not a complete revision archive. If an
    update is late, its earlier value remains unknown. This conservatively masks
    the whole daily statistic rather than substituting a later revision.
    """
    rows = keys[KEYS].copy().reset_index(drop=True)
    if rows.empty or rows.isna().any().any() or rows.duplicated(KEYS).any():
        raise ValueError("Forecast keys must be nonempty, complete and unique")
    for col in ("issue_ts", "target_ts_utc"):
        if not isinstance(rows[col].dtype, pd.DatetimeTZDtype):
            raise TypeError(f"{col} must be timezone-aware")
        rows[col] = rows[col].dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
    issues = rows.issue_ts.dt.tz_convert(config.LOCAL_TZ)
    targets = rows.target_ts_utc.dt.tz_convert(config.LOCAL_TZ)
    idays = issues.dt.tz_localize(None).dt.normalize()
    tdays = targets.dt.tz_localize(None).dt.normalize()
    if not (
        issues.dt.hour.eq(config.ISSUE_HOUR)
        & issues.dt.minute.eq(0)
        & issues.dt.second.eq(0)
        & issues.dt.microsecond.eq(0)
        & rows.horizon_days.isin(config.HORIZONS_DAYS)
        & tdays.sub(idays).dt.days.eq(rows.horizon_days)
    ).all():
        raise ValueError("Forecast keys violate the configured issue time or horizon")

    source = generation.loc[
        generation.area_code.eq(config.BIDDING_ZONE) & generation.production_type.isin(FUELS)
    ].copy()
    if source.empty or source.updated_at_utc.isna().any():
        raise ValueError("No renewable observations or missing update timestamps")
    if not isinstance(source.ts_utc.dtype, pd.DatetimeTZDtype) or not isinstance(
        source.updated_at_utc.dtype, pd.DatetimeTZDtype
    ):
        raise TypeError("Source timestamps must be timezone-aware")
    if source.duplicated(["production_type", "ts_utc"]).any():
        raise ValueError("Duplicate source quarter-hour keys")
    if not source.resolution.eq("PT15M").all():
        raise ValueError("Expected quarter-hourly generation observations")
    values = pd.to_numeric(source.generation_mw, errors="raise")
    if not np.isfinite(values).all() or values.lt(0).any():
        raise ValueError("Generation values must be finite and nonnegative")
    if source.updated_at_utc.lt(source.ts_utc + pd.Timedelta(minutes=15)).any():
        raise ValueError("An actual value was updated before its delivery interval ended")
    hourly = {}
    for fuel, label in FUELS.items():
        part = complete_hours(source.loc[source.production_type.eq(fuel)], "generation_mw")
        hourly[label] = part.set_index("ts_utc")[["generation_mw", "updated_at_utc"]]

    daily = []
    for issue in pd.DatetimeIndex(rows.issue_ts.unique()).sort_values():
        day = issue.tz_convert(config.LOCAL_TZ).date() - pd.Timedelta(days=1)
        start = pd.Timestamp(day, tz=config.LOCAL_TZ).tz_convert("UTC")
        end = pd.Timestamp(day + pd.Timedelta(days=1), tz=config.LOCAL_TZ).tz_convert("UTC")
        hours = pd.date_range(start, end, freq="h", inclusive="left")
        record = {"issue_ts": issue, "source_day_start_utc": start, "expected_hours": len(hours)}
        for label, table in hourly.items():
            subset = table.reindex(hours)
            known = subset.generation_mw.notna() & subset.updated_at_utc.le(issue)
            record[f"{label}_known_hours"] = int(known.sum())
            full = bool(known.all())
            record[f"{label}_updated_at_utc"] = subset.updated_at_utc.max() if full else pd.NaT
            record[f"{label}_daily_mw"] = (
                (subset.generation_mw.max() if label == "solar" else subset.generation_mw.mean())
                if full else np.nan
            )
        daily.append(record)
    return rows.merge(pd.DataFrame(daily), on="issue_ts", how="left", validate="many_to_one", sort=False)


def build(*, replace_existing: bool = False) -> None:
    if config.DATA_MODE != "real":
        raise SystemExit("Use GRIDSENSE_DATA=real to build renewable handoff")
    training = config.PROCESSED_DIR / "training_table.parquet"
    source = config.PROCESSED_DIR / "entsoe_file_library/generation.parquet"
    keys = pd.read_parquet(training, columns=KEYS)
    result = build_handoff(keys, pd.read_parquet(source))
    split = assign_split(result.target_ts_utc)
    # Availability is an input-quality count, not model evaluation.
    coverage = {
        name: {
            "rows": int(split.eq(name).sum()),
            "solar_available": int((split.eq(name) & result.solar_daily_mw.notna()).sum()),
            "wind_available": int((split.eq(name) & result.wind_daily_mw.notna()).sum()),
        }
        for name in ("train", "val")
    }
    output = "renewable_generation_asof.parquet"
    manifest_name = "renewable_generation_asof_manifest.json"
    with TemporaryDirectory(prefix=".renewable-asof-", dir=config.PROCESSED_DIR) as tmp:
        staged = Path(tmp)
        result.to_parquet(staged / output, index=False)
        manifest = {
            "inputs_sha256": {"training_table.parquet": sha256_file(training),
                              "entsoe_file_library/generation.parquet": sha256_file(source)},
            "output_sha256": sha256_file(staged / output),
            "rows": len(result),
            "key": KEYS,
            "train_validation_coverage": coverage,
            "selection": "Complete D-1 Romanian local day; every quarter-hour latest update <= issue",
            "limitation": "Latest recorded values only; historical revision and publication history incomplete.",
        }
        (staged / manifest_name).write_text(json.dumps(manifest, indent=2) + "\n")
        install_staged(
            staged, config.PROCESSED_DIR, [output, manifest_name], replace_existing=replace_existing
        )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace-existing", action="store_true", help="Replace reviewed, differing outputs"
    )
    args = parser.parse_args()
    build(replace_existing=args.replace_existing)
