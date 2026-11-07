"""Prepare, smoke-test and resume a sequential validation-only experiment queue.

Preparation is strictly cache-only. It snapshots labelled train/validation rows,
records code/source checksums and leaves normal model artifacts untouched. Every
job has its own logs/reports and a verified completion marker. No automatic
feature promotion, final refit, test evaluation, commit or push occurs here.
"""

import argparse
import fcntl
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path

import pandas as pd

from gridsense import config, io
from gridsense.features.build import EXTRA_WEATHER_VARS, build_training_table, drop_untrainable
from gridsense.features.regional import (
    REGIONAL_COLUMNS,
    REGIONAL_LOAD_COLUMNS,
    join_regional_features,
    read_regional_table,
)
from gridsense.features.weather_grid import fetch_grid, grid_features, join_grid_features
from gridsense.models.chronological import PROFILES, default_score_months, digest, month_fold
from gridsense.splits import assign_split

VARIANTS = ("current", "weather_extra", "ro_grid", "ro_hu_bg_grid",
            "regional_prices", "regional_load")
SOURCES = ("training_table.parquet", "prices_hourly.parquet", "grid_hourly.parquet",
           "calendar.parquet", "weather_fc.parquet", "regional_market_features.parquet",
           "regional_market_manifest.json")


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def code_fingerprint() -> dict:
    root = repository_root()
    files = sorted((root / "src" / "gridsense").rglob("*.py"))
    files += [root / "pyproject.toml"]
    return {str(path.relative_to(root)): digest(path) for path in files}


def production_inventory() -> dict:
    """Metadata/content statistics detect normal artifact replacement without loading weights."""
    result = {}
    for name in ("lgbm_quantile", "lgbm_classifier"):
        directory = config.MODELS_DIR / name
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                info = path.stat()
                result[str(path.relative_to(config.MODELS_DIR))] = [info.st_size, info.st_mtime_ns]
    return result


def source_hashes() -> dict:
    return {name: digest(config.PROCESSED_DIR / name) for name in SOURCES
            if (config.PROCESSED_DIR / name).is_file()}


def runtime_versions() -> dict:
    return {"python": platform.python_version(), "packages": {
        name: importlib.metadata.version(name)
        for name in ("pandas", "numpy", "pyarrow", "scikit-learn", "lightgbm", "holidays")}}


def experiment_tables(variants: list[str]) -> dict[str, pd.DataFrame]:
    stored = io.read("training_table")
    rebuilt, _ = drop_untrainable(build_training_table(
        io.read("prices_hourly"), io.read("grid_hourly"), io.read("weather_fc"), io.read("calendar")))
    pd.testing.assert_frame_equal(stored, rebuilt)
    extras = tuple(f"f_{name}_" for name in EXTRA_WEATHER_VARS.values())
    forbidden = [column for column in stored if column.startswith(
        (*extras, "f_wgrid_", "f_load_fc_")) or column in REGIONAL_COLUMNS]
    if forbidden:
        raise ValueError(f"Queue control must be the non-opt-in default table, found {forbidden}")
    allowed = assign_split(stored.target_ts_utc).isin(["train", "val"]) & stored.y_price.notna()
    current = stored[allowed].copy()
    result = {"current": current}
    if "weather_extra" in variants:
        table, _ = drop_untrainable(build_training_table(
            io.read("prices_hourly"), io.read("grid_hourly"), io.read("weather_fc"),
            io.read("calendar"), weather_extra=True))
        pd.testing.assert_frame_equal(table[stored.columns], stored)
        result["weather_extra"] = table.loc[current.index].copy()
    if any(name in variants for name in ("ro_grid", "ro_hu_bg_grid")):
        start = pd.Timestamp(config.TRAIN_START.date(), tz=config.LOCAL_TZ).tz_convert("UTC")
        end = (pd.Timestamp(config.VAL_END.date()) + pd.Timedelta(days=1)).tz_localize(
            config.LOCAL_TZ).tz_convert("UTC")
        grid = fetch_grid(start, end, io.read("weather_fc"), cache_only=True)
        for name, countries in (("ro_grid", ("ro",)), ("ro_hu_bg_grid", ("ro", "hu", "bg"))):
            if name in variants:
                result[name] = join_grid_features(current, grid_features(grid, countries))
    if any(name in variants for name in ("regional_prices", "regional_load")):
        regional, _ = read_regional_table()
        joined, _ = join_regional_features(current, regional)
        for name, columns in (("regional_prices", set(REGIONAL_COLUMNS) - set(REGIONAL_LOAD_COLUMNS)),
                              ("regional_load", set(REGIONAL_LOAD_COLUMNS))):
            if name in variants:
                # Keep quality semantics and all original features identical to the control.
                result[name] = current.join(joined[sorted(columns)])
    return {name: result[name] for name in variants}


def prepare(run_dir: Path, variants: list[str], profiles: list[str], months: list[str]) -> dict:
    if run_dir.exists():
        raise ValueError("Choose a new run directory; preparation never overwrites an existing run")
    inputs_before, models_before = source_hashes(), production_inventory()
    code_before = code_fingerprint()
    tables = experiment_tables(variants)
    folds = {name: [month_fold(table, month)[1] for month in months]
             for name, table in tables.items()}
    run_dir.mkdir(parents=True)
    snapshots = run_dir / "inputs"
    snapshots.mkdir()
    hashes = {}
    for name, table in tables.items():
        path = snapshots / f"{name}.parquet"
        table.to_parquet(path, index=True)
        hashes[name] = digest(path)
        # A read-only input plus checksums protects accidental writes as well as resume.
        path.chmod(0o444)
    if inputs_before != source_hashes() or models_before != production_inventory():
        raise RuntimeError("Shared inputs or production models changed while preparing snapshots")
    if code_before != code_fingerprint():
        raise RuntimeError("Code changed while preparing the queue")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository_root(),
                                       text=True).strip()
    plan = {"prepared_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "git_commit": revision,
            "runtime_versions": runtime_versions(),
            "code_sha256": code_before, "source_sha256": inputs_before,
            "production_inventory": models_before, "snapshot_sha256": hashes,
            "test_evaluated": False, "months": months, "folds": folds,
            "jobs": [{"id": f"{variant}__{profile}", "variant": variant, "profile": profile}
                     for variant in variants for profile in profiles]}
    atomic_json(run_dir / "plan.json", plan)
    print(f"Prepared {len(plan['jobs'])} sequential jobs / {len(months)} score months: {run_dir}")
    return plan


def verify_plan(run_dir: Path, plan: dict) -> None:
    if "runtime_versions" in plan and plan["runtime_versions"] != runtime_versions():
        raise ValueError("Python/package versions differ from the prepared queue")
    if plan["code_sha256"] != code_fingerprint():
        raise ValueError("Code differs from the prepared queue; prepare a new run")
    if plan["source_sha256"] != source_hashes():
        raise ValueError("Shared source inputs differ from the prepared queue")
    if plan["production_inventory"] != production_inventory():
        raise ValueError("Production model artifacts differ from the prepared queue")
    for name, checksum in plan["snapshot_sha256"].items():
        if digest(run_dir / "inputs" / f"{name}.parquet") != checksum:
            raise ValueError(f"Snapshot checksum mismatch: {name}")


def valid_completion(directory: Path, checksum: str, *, months: list[str], profile: str,
                     smoke: bool) -> bool:
    marker = directory / "completed.json"
    if not marker.is_file():
        return False
    value = json.loads(marker.read_text())
    if (value["input_sha256"] != checksum or value["profile"] != profile
            or value["smoke_only"] != smoke or value["test_evaluated"]):
        raise ValueError("Completion marker does not match the queued job")
    if [fold["score_month"] for fold in value["folds"]] != months:
        raise ValueError("Completion marker has different scoring months")
    for name, report_hash in value["report_sha256"].items():
        if digest(directory / name) != report_hash:
            raise ValueError("Completed report checksum mismatch")
    return True


def execute(run_dir: Path, *, smoke: bool = False) -> None:
    plan = json.loads((run_dir / "plan.json").read_text())
    with (run_dir / "queue.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another process is already executing this queue") from error
        if not smoke:
            first = plan["jobs"][0]
            if not valid_completion(run_dir / "smoke" / first["id"],
                                    plan["snapshot_sha256"][first["variant"]],
                                    months=plan["months"][:1], profile=first["profile"], smoke=True):
                raise RuntimeError("Run and verify the smoke test before executing the full queue")
        jobs = plan["jobs"][:1] if smoke else plan["jobs"]
        months = plan["months"][:1] if smoke else plan["months"]
        mode = "smoke" if smoke else "jobs"
        for job in jobs:
            verify_plan(run_dir, plan)
            directory = run_dir / mode / job["id"]
            checksum = plan["snapshot_sha256"][job["variant"]]
            if valid_completion(directory, checksum, months=months, profile=job["profile"], smoke=smoke):
                print(f"Verified completed job, skipping: {job['id']}", flush=True)
                continue
            directory.mkdir(parents=True, exist_ok=True)
            atomic_json(run_dir / "status.json", {"state": "running", "job": job["id"], "smoke": smoke})
            command = ["uv", "run", "python", "-m", "gridsense.models.chronological",
                       "--input", str(run_dir / "inputs" / f"{job['variant']}.parquet"),
                       "--output", str(directory), "--sha256", checksum,
                       "--profile", job["profile"], "--months", *months]
            if smoke:
                command.append("--smoke")
            print(f"Starting {job['id']} ({mode}); log: {directory / 'run.log'}", flush=True)
            with (directory / "run.log").open("w") as log:
                result = subprocess.run(command, check=False, cwd=repository_root(), stdout=log,
                                        stderr=subprocess.STDOUT,
                                        env=os.environ | {"GRIDSENSE_DATA": "real", "PYTHONUNBUFFERED": "1"})
            if result.returncode:
                atomic_json(run_dir / "status.json", {"state": "failed", "job": job["id"],
                                                     "exit_code": result.returncode, "smoke": smoke})
                raise RuntimeError(f"Job failed; inspect {directory / 'run.log'}")
            verify_plan(run_dir, plan)
            if not valid_completion(directory, checksum, months=months, profile=job["profile"], smoke=smoke):
                raise RuntimeError("Job exited without a verified completion report")
        atomic_json(run_dir / "status.json", {"state": "smoke_passed" if smoke else "completed",
                                             "jobs": len(jobs), "test_evaluated": False})
        print("Smoke passed; full queue not started." if smoke else "All queued jobs completed.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=["default"])
    parser.add_argument("--months", nargs="+", default=default_score_months())
    args = parser.parse_args(argv)
    if config.DATA_MODE != "real":
        parser.error("Use GRIDSENSE_DATA=real for overnight development experiments")
    if sum((args.prepare, args.execute, args.smoke)) != 1:
        parser.error("Choose exactly one of --prepare, --smoke or --execute")
    if args.prepare:
        prepare(args.run_dir.resolve(), args.variants, args.profiles, args.months)
    else:
        execute(args.run_dir.resolve(), smoke=args.smoke)


if __name__ == "__main__":
    main()