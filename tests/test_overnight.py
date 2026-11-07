import fcntl
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridsense import config
from gridsense.models import overnight
from gridsense.splits import assign_split


def _checksum(path):
    """Independent checksums of tiny temporary files, never real input/model files."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _completion(directory, checksum, months, *, profile="default", smoke=False):
    directory.mkdir(parents=True, exist_ok=True)
    report = directory / "price.csv"
    report.write_text("score_month,value\n" + "".join(f"{month},1\n" for month in months))
    value = {
        "input_sha256": checksum,
        "profile": profile,
        "smoke_only": smoke,
        "test_evaluated": False,
        "production_artifacts_changed": False,
        "folds": [{"score_month": month} for month in months],
        "report_sha256": {report.name: _checksum(report)},
    }
    (directory / "completed.json").write_text(json.dumps(value))
    return value


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """All fingerprints and inventory checks operate on a tiny synthetic repository."""
    root = tmp_path / "repo"
    code = root / "src" / "gridsense" / "stub.py"
    code.parent.mkdir(parents=True)
    code.write_text("# Synthetic code fingerprint fixture.\n")
    (root / "pyproject.toml").write_text('[project]\nname = "synthetic"\n')
    monkeypatch.setattr(overnight, "repository_root", lambda: root)
    for name in ("PROCESSED_DIR", "MODELS_DIR", "REPORTS_DIR"):
        directory = root / name.lower()
        directory.mkdir()
        monkeypatch.setattr(config, name, directory)
    source = config.PROCESSED_DIR / "training_table.parquet"
    source.write_bytes(b"synthetic source fingerprint; not a real parquet")
    model = config.MODELS_DIR / "lgbm_quantile" / "synthetic" / "model.joblib"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"synthetic inventory stub; not model weights")
    return {"root": root, "code": code, "source": source, "model": model}


@pytest.fixture
def queue(sandbox):
    run_dir = sandbox["root"] / "run"
    inputs = run_dir / "inputs"
    inputs.mkdir(parents=True)
    variants = ["current", "weather_extra"]
    hashes = {}
    for variant in variants:
        snapshot = inputs / f"{variant}.parquet"
        snapshot.write_bytes(f"synthetic {variant} snapshot".encode())
        hashes[variant] = _checksum(snapshot)
    plan = {
        "code_sha256": overnight.code_fingerprint(),
        "source_sha256": overnight.source_hashes(),
        "production_inventory": overnight.production_inventory(),
        "snapshot_sha256": hashes,
        "months": overnight.default_score_months()[:2],
        "jobs": [{"id": f"{variant}__default", "variant": variant, "profile": "default"}
                 for variant in variants],
        "test_evaluated": False,
    }
    overnight.atomic_json(run_dir / "plan.json", plan)
    return run_dir, plan


@pytest.fixture
def development_rows():
    days = pd.date_range(config.TRAIN_START.normalize(), config.VAL_END.normalize(), freq="D")
    price = np.where(np.arange(len(days)) % 2,
                     config.CHEAP_THRESHOLD_EUR - 1, config.NEAR_ZERO_THRESHOLD_EUR + 30)
    return pd.DataFrame({
        "issue_ts": (days - pd.DateOffset(days=1)
                     + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_convert("UTC"),
        "target_ts_utc": (days + pd.Timedelta(hours=6)).tz_convert("UTC"),
        "horizon_days": min(config.HORIZONS_DAYS),
        "y_price": price,
        "y_near_zero": price <= config.NEAR_ZERO_THRESHOLD_EUR,
        "y_cheap": price <= config.CHEAP_THRESHOLD_EUR,
        "f_signal": 1.0,
    })


def _outside_row(table, kind):
    row = table.iloc[[0]].copy()
    day = (config.TEST_START if kind == "test"
           else config.VAL_END.normalize() + pd.DateOffset(days=1))
    row["target_ts_utc"] = (day + pd.Timedelta(hours=6)).tz_convert("UTC")
    row["issue_ts"] = (day - pd.DateOffset(days=1)
                       + pd.Timedelta(hours=config.ISSUE_HOUR)).tz_convert("UTC")
    return row


def test_valid_completion_requires_marker_and_untampered_report(tmp_path):
    directory = tmp_path / "job"
    months = overnight.default_score_months()[:1]
    arguments = {"months": months, "profile": "default", "smoke": False}
    assert not overnight.valid_completion(directory, "snapshot-hash", **arguments)
    _completion(directory, "snapshot-hash", months)
    assert overnight.valid_completion(directory, "snapshot-hash", **arguments)
    (directory / "price.csv").write_text("tampered report\n")
    with pytest.raises(ValueError, match="Completed report checksum mismatch"):
        overnight.valid_completion(directory, "snapshot-hash", **arguments)


@pytest.mark.parametrize("changed", ["input_sha256", "profile", "test_evaluated", "folds"])
def test_valid_completion_rejects_wrong_job_or_months(tmp_path, changed):
    months = overnight.default_score_months()[:1]
    directory = tmp_path / "job"
    marker = _completion(directory, "snapshot-hash", months)
    marker[changed] = {
        "input_sha256": "another-snapshot",
        "profile": "recent",
        "test_evaluated": True,
        "folds": [{"score_month": overnight.default_score_months()[1]}],
    }[changed]
    (directory / "completed.json").write_text(json.dumps(marker))
    with pytest.raises(ValueError, match="Completion marker"):
        overnight.valid_completion(directory, "snapshot-hash", months=months,
                                   profile="default", smoke=False)


@pytest.mark.parametrize("marker_smoke", [False, True])
def test_valid_completion_never_confuses_smoke_and_full(tmp_path, marker_smoke):
    months = overnight.default_score_months()[:1]
    directory = tmp_path / "job"
    _completion(directory, "snapshot-hash", months, smoke=marker_smoke)
    with pytest.raises(ValueError, match="Completion marker does not match"):
        overnight.valid_completion(directory, "snapshot-hash", months=months,
                                   profile="default", smoke=not marker_smoke)


@pytest.mark.parametrize(("changed", "message"), [
    ("code", "Code differs"),
    ("source", "Shared source inputs differ"),
    ("model", "Production model artifacts differ"),
    ("new_model", "Production model artifacts differ"),
    ("snapshot", "Snapshot checksum mismatch"),
])
def test_verify_plan_rejects_changed_fingerprints_and_inventory(queue, sandbox, changed, message):
    run_dir, plan = queue
    overnight.verify_plan(run_dir, plan)
    if changed in ("code", "source", "model"):
        sandbox[changed].write_bytes(b"changed synthetic content and size")
    elif changed == "new_model":
        added = config.MODELS_DIR / "lgbm_classifier" / "new" / "model.joblib"
        added.parent.mkdir(parents=True)
        added.write_bytes(b"another synthetic inventory entry")
    else:
        (run_dir / "inputs" / "current.parquet").write_bytes(b"tampered snapshot")
    with pytest.raises(ValueError, match=message):
        overnight.verify_plan(run_dir, plan)


def test_execute_smoke_runs_only_first_job_and_month_and_resumes(queue, sandbox, monkeypatch):
    run_dir, plan = queue
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[:5] == ["uv", "run", "python", "-m", "gridsense.models.chronological"]
        assert kwargs["cwd"] == sandbox["root"]
        assert kwargs["env"]["GRIDSENSE_DATA"] == "real"
        assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"
        assert kwargs["stderr"] == subprocess.STDOUT
        assert not kwargs["stdout"].closed
        directory = Path(command[command.index("--output") + 1])
        checksum = command[command.index("--sha256") + 1]
        profile = command[command.index("--profile") + 1]
        months = command[command.index("--months") + 1:command.index("--smoke")]
        assert months == plan["months"][:1]
        assert directory == run_dir / "smoke" / plan["jobs"][0]["id"]
        assert Path(command[command.index("--input") + 1]) == (
            run_dir / "inputs" / f"{plan['jobs'][0]['variant']}.parquet"
        )
        _completion(directory, checksum, months, profile=profile, smoke=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(overnight.subprocess, "run", run)
    overnight.execute(run_dir, smoke=True)
    assert len(calls) == 1
    assert not (run_dir / "jobs").exists()
    assert not (run_dir / "smoke" / plan["jobs"][1]["id"]).exists()
    assert json.loads((run_dir / "status.json").read_text()) == {
        "state": "smoke_passed", "jobs": 1, "test_evaluated": False,
    }
    overnight.execute(run_dir, smoke=True)
    assert len(calls) == 1  # Verified completion, not a second subprocess.


def test_execute_refuses_a_queue_locked_by_another_executor(queue, monkeypatch):
    run_dir, _ = queue
    monkeypatch.setattr(overnight.subprocess, "run", lambda *args, **kwargs: pytest.fail(
        "A locked queue must not launch a subprocess"))
    with (run_dir / "queue.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="Another process is already executing"):
            overnight.execute(run_dir, smoke=True)


def test_experiment_tables_filters_test_and_unassigned_rows(development_rows, monkeypatch):
    stored = pd.concat([development_rows, _outside_row(development_rows, "test"),
                        _outside_row(development_rows, "unassigned")], ignore_index=True)
    monkeypatch.setattr(overnight.io, "read", lambda name: (
        stored.copy() if name == "training_table" else pd.DataFrame()))
    monkeypatch.setattr(overnight, "build_training_table", lambda *args, **kwargs: stored.copy())
    monkeypatch.setattr(overnight, "drop_untrainable", lambda table: (table, {}))
    snapshots = overnight.experiment_tables(["current"])
    pd.testing.assert_frame_equal(snapshots["current"], stored.loc[development_rows.index])
    assert assign_split(snapshots["current"].target_ts_utc).isin(["train", "val"]).all()


def test_prepare_writes_read_only_development_snapshot_and_validated_folds(
        sandbox, development_rows, monkeypatch):
    monkeypatch.setattr(overnight, "experiment_tables", lambda variants: {
        "current": development_rows.copy(),
    })
    monkeypatch.setattr(overnight.subprocess, "check_output", lambda *args, **kwargs: "synthetic-sha\n")
    run_dir = sandbox["root"] / "prepared"
    months = overnight.default_score_months()[:2]
    plan = overnight.prepare(run_dir, ["current"], ["default"], months)
    snapshot = run_dir / "inputs" / "current.parquet"
    pd.testing.assert_frame_equal(pd.read_parquet(snapshot), development_rows)
    assert snapshot.stat().st_mode & 0o222 == 0
    assert plan["snapshot_sha256"]["current"] == _checksum(snapshot)
    assert [fold["score_month"] for fold in plan["folds"]["current"]] == months
    assert plan["test_evaluated"] is False
    assert plan["jobs"] == [{"id": "current__default", "variant": "current", "profile": "default"}]
    overnight.verify_plan(run_dir, plan)


@pytest.mark.parametrize("invalid_split", ["test", "unassigned"])
def test_prepare_fold_validation_rejects_non_development_snapshot(
        sandbox, development_rows, monkeypatch, invalid_split):
    unsafe = pd.concat([development_rows, _outside_row(development_rows, invalid_split)],
                       ignore_index=True)
    monkeypatch.setattr(overnight, "experiment_tables", lambda variants: {"current": unsafe})
    monkeypatch.setattr(overnight.subprocess, "check_output", lambda *args, **kwargs: pytest.fail(
        "Unsafe snapshots must be rejected before recording a revision"))
    run_dir = sandbox["root"] / "rejected"
    with pytest.raises(ValueError, match="labelled train/validation rows only"):
        overnight.prepare(run_dir, ["current"], ["default"], overnight.default_score_months()[:1])
    assert not (run_dir / "plan.json").exists()