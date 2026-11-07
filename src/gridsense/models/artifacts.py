import json
import subprocess
from datetime import UTC, datetime

import joblib
import pandas as pd

from gridsense import config


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "nogit"
    return result.stdout.strip()


def new_version() -> str:
    # Timestamp first so lexical order is chronological.
    return f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{_git_sha()}"


def save(model, metadata: dict) -> str:
    version = new_version()
    out = config.MODELS_DIR / model.name / version
    out.mkdir(parents=True)
    joblib.dump(model, out / "model.joblib")
    meta = {"name": model.name, "version": version, "data_mode": config.DATA_MODE, **metadata}
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, default=str))
    return version


def load_latest(name: str):
    versions = sorted(p for p in (config.MODELS_DIR / name).iterdir() if p.is_dir())
    if not versions:
        raise FileNotFoundError(f"no trained versions of {name} in {config.MODELS_DIR}")
    return joblib.load(versions[-1] / "model.joblib"), versions[-1].name


def log_experiment(row: dict) -> None:
    path = config.REPORTS_DIR / "experiments.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    log = pd.DataFrame([row])
    if path.exists():
        log = pd.concat([pd.read_csv(path), log], ignore_index=True)
    log.to_csv(path, index=False)
