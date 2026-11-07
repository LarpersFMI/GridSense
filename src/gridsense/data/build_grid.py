"""Build the Romanian grid_hourly contract from the regional real-load dataset."""

import argparse

import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.data.price_features import utc_hours
from gridsense.schemas import GRID_HOURLY


def grid_from_regional_load(load: pd.DataFrame) -> pd.DataFrame:
    """Select real Romanian load and leave uncollected generation values missing."""
    required = {"country_code", "ts_utc", "load_actual_mw"}
    if missing := required - set(load.columns):
        raise ValueError(f"Regional load is missing columns: {sorted(missing)}")
    grid = load.loc[load["country_code"].eq("RO"), ["ts_utc", "load_actual_mw"]].copy()
    if grid.empty:
        raise ValueError("Regional load contains no Romanian observations")
    grid["ts_utc"] = utc_hours(grid["ts_utc"], "regional_load_hourly.ts_utc")
    if grid["ts_utc"].duplicated().any():
        raise ValueError("Regional load contains duplicate Romanian hours")
    grid["load_actual_mw"] = pd.to_numeric(grid["load_actual_mw"], errors="raise")
    if not (np.isfinite(grid["load_actual_mw"]) & grid["load_actual_mw"].ge(0)).all():
        raise ValueError("Romanian load must contain finite, nonnegative values")
    grid["solar_actual_mw"] = np.nan
    grid["wind_actual_mw"] = np.nan
    return grid[list(GRID_HOURLY)].astype(GRID_HOURLY).sort_values("ts_utc", ignore_index=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real for the real Romanian grid table")

    source = config.PROCESSED_DIR / "regional_load_hourly.parquet"
    destination = config.PROCESSED_DIR / "grid_hourly.parquet"
    try:
        grid = grid_from_regional_load(pd.read_parquet(source))
        if destination.exists():
            current = io.read("grid_hourly")
            if not current.equals(grid):
                raise ValueError(
                    f"{destination} already contains different data. Preserve and reconcile "
                    "it before rebuilding."
                )
            print(f"Existing grid_hourly matches: {len(grid):,} rows")
            return
        io.write(grid, "grid_hourly")
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Romanian grid build failed: {exc}\n")

    print(f"grid_hourly.parquet: {len(grid):,} rows, {grid.ts_utc.min()} to {grid.ts_utc.max()}")


if __name__ == "__main__":
    main()
