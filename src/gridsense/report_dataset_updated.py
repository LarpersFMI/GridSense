"""Tells the GridSense server that rows were appended to a dataset's file, so the Watchdog checks the triggers on it.

    uv run python -m gridsense.report_dataset_updated predictions --path data/processed/predictions.parquet --model-version lgbm-0
    uv run python -m gridsense.report_dataset_updated prices

predictions: reports one run (POST /internal/runs). The run is the file's latest issue_ts unless --issue-ts says which.
prices: reports that a day's cleared prices were appended (POST /internal/datasets/prices/updates).

Each trigger finds its own new rows (past its watermark on its incremental column), so the request says only which
dataset changed. Call it after the parquet is fully written, never before: the Watchdog reads the file as soon as
it's told. Every run appends to the same predictions file.

The server is GRIDSENSE_SERVER_URL (.env, default http://localhost:4000). --dry-run prints the request instead.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from gridsense.config import ROOT

load_dotenv(ROOT / ".env")

SERVER_URL = os.environ.get("GRIDSENSE_SERVER_URL", "http://localhost:4000")


def run_report(path: Path, model_version: str, issue_ts: pd.Timestamp | None = None) -> dict:
    """The body of POST /internal/runs for one run in a predictions file (Forecaster.Run.Report)."""
    issues = pd.read_parquet(path, columns=["issue_ts"])["issue_ts"]

    if issue_ts is None:
        issue_ts = issues.max()

    rows = int((issues == issue_ts).sum())

    if rows == 0:
        raise SystemExit(f"No rows with issue_ts {issue_ts.isoformat()} in {path}")

    return {
        "issueTs":         issue_ts.isoformat(),
        "modelVersion":    model_version,
        "rows":            rows,
        "predictionsPath": str(path.resolve()),
    }


def post(route: str, body: dict | None = None) -> dict:
    response = requests.post(f"{SERVER_URL}{route}", json=body, timeout=30)

    if not response.ok:
        raise SystemExit(f"{response.status_code} from {route}: {response.text}")

    return response.json()


def report_run(path: Path, model_version: str, issue_ts: pd.Timestamp | None = None) -> dict:
    """Reports a run: the server records it and tells the Watchdog the predictions changed. Again for the same issue_ts: a no-op."""
    return post("/internal/runs", run_report(path, model_version, issue_ts))["run"]


def report_dataset_updated(dataset: str) -> dict:
    """Reports that rows were appended to a dataset's file outside a run: a day's cleared prices."""
    return post(f"/internal/datasets/{dataset}/updates")["update"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the request, don't send it")
    datasets = parser.add_subparsers(dest="dataset", required=True)

    predictions = datasets.add_parser("predictions", help="report a run")
    predictions.add_argument("--path", type=Path, required=True)
    predictions.add_argument("--model-version", required=True)
    predictions.add_argument("--issue-ts", type=lambda value: pd.Timestamp(value).tz_convert("UTC"),
                             help="ISO with offset, e.g. 2026-05-13T07:00:00Z (default: the file's latest)")

    datasets.add_parser("prices", help="report a day's cleared prices appended")

    args = parser.parse_args()

    if args.dataset == "predictions":
        route, body = "/internal/runs", run_report(args.path, args.model_version, args.issue_ts)
    else:
        route, body = f"/internal/datasets/{args.dataset}/updates", None

    if args.dry_run:
        print(f"POST {SERVER_URL}{route}")
        print(json.dumps(body, indent=2))

        return

    print(json.dumps(post(route, body), indent=2))


if __name__ == "__main__":
    main()
