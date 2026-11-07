"""Where pipelines write: the dataset files in DATASET_DIR (.env), the same the server and the Watchdog read."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from gridsense.config import ROOT
from gridsense.report_dataset_updated import report_dataset_updated, report_run

load_dotenv(ROOT / ".env")

DATASET_DIR = (ROOT / os.environ.get("DATASET_DIR", "data/processed")).resolve()

# As Dataset.Predictions.FILE, Dataset.PricesHourly.FILE and Dataset.Features.FILE on the TypeScript side.
FILES = {
    "predictions": "predictions.parquet",
    "prices":      "prices_hourly.parquet",
    "features":    "features.parquet",
}

# The datasets triggers are checked on (Dataset.Triggerable): an append to these is reported, so the Watchdog checks
# them. `features` is for looking at: written, never reported.
REPORTED = ("predictions", "prices")

# The line that tells the PipelineRunner what a run appended (PythonService.MARKER); left out of the log.
MARKER = "@@gridsense "


def path(dataset: str) -> Path:
    return DATASET_DIR / FILES[dataset]


def read(dataset: str) -> pd.DataFrame | None:
    """The dataset as it is now; None while it has no file."""
    if not path(dataset).exists():
        return None

    return pd.read_parquet(path(dataset))


class Run:
    """One run of a pipeline: what it appends is written whole, reported to the server, and counted for the UI."""

    def append(self, dataset: str, rows: pd.DataFrame, *, key: list[str], model_version: str | None = None) -> int:
        """Appends the rows whose key isn't in the file yet; returns how many. Rows already there are left as they are,
        so running a pipeline twice appends nothing the second time.

        predictions: one run per call (one issue_ts), reported with its model_version (POST /internal/runs).
        """
        target = path(dataset)
        current = read(dataset)

        if current is not None:
            known = pd.MultiIndex.from_frame(current[key])
            rows = rows[~pd.MultiIndex.from_frame(rows[key]).isin(known)]

        if rows.empty:
            print(f"{dataset}: nothing new")

            return 0

        merged = rows if current is None else pd.concat([current, rows], ignore_index=True)

        # Whole, then renamed into place: the Watchdog never reads a half-written file.
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".partial")
        merged.to_parquet(partial, index=False)
        os.replace(partial, target)

        if dataset == "predictions":
            report_run(target, model_version or "unknown", rows["issue_ts"].max())
        elif dataset in REPORTED:
            report_dataset_updated(dataset)

        print(f"{dataset}: {len(rows)} rows appended" + (" and reported" if dataset in REPORTED else ""))
        print(MARKER + json.dumps({"rowsAppended": {dataset: len(rows)}}), flush=True)

        return len(rows)
