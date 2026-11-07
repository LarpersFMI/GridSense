# D+1 teammate handoff

The compressed [input/report archive](teammate-d1-dev365-inputs.tar.gz) is now
tracked in Git on `dev`. No AirDrop is required. Size: approximately 14 MB.
[SHA256](teammate-d1-dev365-inputs.sha256):
`58b06d5d57b948f81b93a61035d1acabc4f629ef64981e1c22f9a8c7ca6e32a3`.

It includes the seven public processed inputs, a reference plan/provenance,
unchanged completed reports for `current__default`, `weather_extra__default` and
`regional_prices__default`, and the earlier completed extra-weather D+1 reports.
It excludes environment files, credentials, raw caches and model weights. Shared
price tables contain public labels beyond development, but the dedicated runner
only fits/scores the configured development periods for these comparisons.

## 1. Download the tracked archive

From a clean/non-running clone (do not pull under a live prepared experiment):

```zsh
git pull --ff-only
shasum -a 256 -c handoffs/teammate-d1-dev365-inputs.sha256
```

Missing completed reports caused `No verified completed hourly reference is
available`. Copying only the plan and snapshots is insufficient. Every report
listed in each unchanged completion marker must be present and match its hash.

## 2. Use the matching training revision

The archive's reference code fingerprint matches **`f22a644b778721a1de5aa9a51808deb39b7cceef`**.
Newer `dev` contains teammate changes to drift, explanations, export and schemas,
which correctly invalidate that fingerprint. Do not change stored hashes to bypass
this. Keep current `dev` for application work and use an isolated training worktree:

```zsh
git worktree add --detach ../GridSense-d1-training f22a644b778721a1de5aa9a51808deb39b7cceef
cp handoffs/teammate-d1-dev365-inputs.tar.gz ../GridSense-d1-training/
cd ../GridSense-d1-training
shasum -a 256 teammate-d1-dev365-inputs.tar.gz
tar -xzf teammate-d1-dev365-inputs.tar.gz
uv sync --frozen
```

Use a new worktree path if that directory exists. Extract only into this fresh,
non-running checkout; do not overwrite another experiment's shared tables. Use
Python 3.11.15 and the package versions from the transferred reference plan.
Never transfer another Mac's virtual environment or its production inventory.

If you already have a verified reference context on this exact revision, skip
preparation below and import only the missing job folders. Do not overwrite its
plan or snapshots. A different code/runtime/data fingerprint needs reconciliation,
not checksum edits.

## 3. Prepare/import the local context

```zsh
GRIDSENSE_DATA=real make overnight-prepare \
  RUN_DIR=reports/real/overnight/teammate-reference-context-dev365 \
  VARIANTS="current weather_extra regional_prices" \
  PROFILES="default"
mkdir -p reports/real/overnight/teammate-reference-context-dev365/jobs
for candidate in current__default weather_extra__default regional_prices__default; do
  destination="reports/real/overnight/teammate-reference-context-dev365/jobs/${candidate}"
  if [[ ! -e "$destination" ]]; then
    cp -R "reports/real/overnight/reference-context-dev365/jobs/${candidate}" "$destination"
  fi
done
```

Preparation creates this Mac's own immutable plan/snapshots and model inventory.
It does not train models. Copied completion markers retain their original provenance;
they are historical reference reports, not new integrated-code scores.

Verify before rerunning setup/training:

```zsh
GRIDSENSE_DATA=real uv run python - <<'PY'
import json
from pathlib import Path
from gridsense.models.overnight import valid_completion, verify_plan

root = Path("reports/real/overnight/teammate-reference-context-dev365")
source = Path("reports/real/overnight/reference-context-dev365")
plan = json.loads((root / "plan.json").read_text())
reference = json.loads((source / "plan.json").read_text())
verify_plan(root, plan)
for key in ("code_sha256", "runtime_versions", "source_sha256"):
    assert plan[key] == reference[key], f"Mismatch: {key}"
for job in plan["jobs"]:
    assert plan["snapshot_sha256"][job["variant"]] == reference["snapshot_sha256"][job["variant"]]
    assert valid_completion(
        root / "jobs" / job["id"], plan["snapshot_sha256"][job["variant"]],
        months=plan["months"], profile=job["profile"], smoke=False,
    ), f"Incomplete reference reports: {job['id']}"
print("Local data/code/runtime and completed reference reports verified.")
PY
```

If any check fails, stop and reconcile the exact source revision, interpreter,
packages, source data or missing reports. Do not relabel reports or edit hash maps.

## 4. Run the two remaining development comparisons

```zsh
caffeinate -i zsh experiments/train_d1.zsh current__default \
  reports/real/overnight/teammate-reference-context-dev365 &&
caffeinate -i zsh experiments/train_d1.zsh regional_prices__default \
  reports/real/overnight/teammate-reference-context-dev365
```

Each creates a fresh timestamped run, performs smoke/full development training,
prints percentage progress and runs the policy-only comparison. A failed first
run prevents the second from starting. Preserve prior partial setup directories;
there is no need to delete them. Both jobs use one training thread and run sequentially.

**Final-test boundary:** Izabela has already completed the explicitly authorized
single final-test evaluation. These remaining runs are development comparisons,
not candidates to re-score on that consumed holdout. The archive was built before
that final evaluation and intentionally contains no final-test results or lock.
The receiving Mac lacking a marker is not permission to evaluate the test again.
Do not run `--final`, `FINAL=1`, remove locks, or use final-test outcomes to tune.
