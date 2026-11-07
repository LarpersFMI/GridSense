# Overnight training plan: two MacBook Pros (M5, 48 GB + 24 GB)

## 1. Objective and current status

**Primary objective:** improve **D+1** slot safety without sacrificing useful offer
volume. Forecast issue time, split dates, label thresholds and data paths remain in
[configuration](../src/gridsense/config.py). The final test is not part of this plan.

Both Macs can train these tabular models. Use **independent experiments on each
machine**, not distributed training of one model. The machines do not provide a
combined 72 GB memory pool. LightGBM here runs on CPU; MPS/Metal/CUDA setup is not
required. More RAM is useful for feature/slot copies, not a guarantee of better models.

Progress snapshot checked **2026-11-07, during final verification of this plan**:

- Original queue: **28 / 28 jobs complete**, or **112 / 112 full folds**.
- Completion state is `completed`; every job's report hashes verify.
- Code/runtime/source/snapshot/production checks and completed-report hashes verify.
- The 48 GB Mac was on battery at the latest check. Reconnect power before leaving
  new training unattended; `caffeinate` does not prevent battery exhaustion.
- D+1, slot-level and policy-stability follow-ups are already complete; do not
  rerun them unchanged just to fill the night.
- Recent repository verification: **297 tests and lint pass**. The D+1 code/tests,
  documentation and VS Code tasks are being published on `ml/d1-training`; both operators
  must check out the same agreed commit before preparing new runs. Ignored input
  tables and reference reports still require the data handoff below.

This is a timestamped status, **not a live progress counter**. Read the
[queue status](../reports/real/overnight/20261107-forecast-recency/status.json)
and corresponding job log for the latest state.

The D+1 training branch preserves the original verified implementation. Remote
`dev` advanced with concurrent server/ML changes before publishing; those are
deliberately not merged into prepared runs. Checkout `ml/d1-training` for this
handoff, rather than assuming latest `dev` reproduces the frozen experiments.

Relevant results/protocols:
[D+1 training](day_ahead_validation.md), [slot comparison](slot_validation.md),
[policy stability](day_ahead_policy.md), and [ML handoff](ml_handoff.md).

## 2. Rules before starting

1. **Do not interrupt or mutate the existing queue.** No pulls, source changes,
   feature rebuilds, dependency updates or production-model replacement in that
    checkout while it executes. Let all remaining jobs finish.
2. Use a **separate clone on each Mac**. Separate experiments use separate new run
   directories. Do not use an iCloud/Dropbox-synchronized directory for live Parquets,
   caches, reports or weights; merge/copy completed artifacts afterward.
3. Freeze the same source commit, experiment scripts, lockfile and processed data.
   A matching Git branch name alone is insufficient. Share local experiment changes
   through an agreed commit or a reviewed, checksummed source archive. Do not transfer
   credentials, environment files, API tokens or the author's virtual environment.
4. **Development only:** inputs must use the canonical train/validation splits.
   Never run final evaluation, delete the test-evaluation marker, or reinterpret the
   refit gap as validation to obtain another attractive score.
5. No automatic model or threshold promotion. The 0.925 fixed-threshold results
   are descriptive development evidence, not a validated deployment winner.

## 3. Hardware and workload allocation

Start with **one training process per Mac**. This is safe and easy to reproduce;
neither RAM size requires two concurrent jobs. The dedicated D+1 runner explicitly
uses one LightGBM thread, while the original chronological queue uses four.
Environment variables below limit ancillary BLAS libraries; they do not override
explicit LightGBM `n_jobs` values. Do not edit threads in a prepared run.

| Machine | Initial allocation | Memory practice |
|---|---|---|
| Your M5 / 48 GB | Larger engineered-feature candidate and a bounded weather-extra recency probe | Keep at least 12 GB free for macOS/editor; investigate sustained worker usage above roughly 30 GB |
| Teammate M5 / 24 GB | Current-feature D+1 control and regional-price D+1 candidate | Keep roughly 8 GB for macOS/editor; investigate sustained worker usage above roughly 14–16 GB |

These are **operating guidelines, not measured peaks or enforced memory limits**.
Check Activity Monitor memory pressure and swap. If pressure turns yellow/red or
swap grows persistently, stop adding concurrent work and reduce concurrency first.
Do not silently discard rows/features or change folds to fit memory. Profile one
smoke/full job before deciding to increase concurrency.

Use AC power, an open lid, adequate ventilation and `caffeinate -i`. It prevents
idle sleep, not shutdown, a closed-lid sleep guarantee, or loss of power. Keep the
VS Code/task terminal or shell running. Both people can inspect completed reports
while training, but avoid separate heavyweight training processes in the same clone.

## 4. Tonight's bounded experiment board

Continue using the existing verified feature snapshots. Do not schedule another
28-job sweep. The existing `weather_extra__chain_730_90` D+1 run is the completed
reference, not a new training job.

| Owner | New reference candidate | Question |
|---|---|---|
| 48 GB, job A1 | `forecast_engineered__chain_730_90` | Do archived engineered inputs improve tomorrow-only ranking/safety versus the completed extras reference? |
| 48 GB, job A2 | `weather_extra__default` | Does equal 365-day classifier recency improve D+1 stability relative to the completed 730-day near-zero reference? |
| 24 GB, job B1 | `current__chain_730_90` | Does the simpler default feature set retain most of the D+1 benefit? |
| 24 GB, job B2 | `regional_prices__chain_730_90` | Do issue-known neighbouring prices improve the difficult D+1 months? |

Each dedicated run trains pooled-hourly, D+1-hourly and D+1-slot predictors and
generates seven forward prediction months, followed by four scoring months.
That is **four independent candidate runs / 84 predictor fits**, excluding smokes.
The pooled predictor is a reference; policy scoring remains **D+1 only**.
The `default` versus `chain_730_90` near-zero contrast is 365 versus 730 days;
the secondary conditional-cheap model is not fitted in this focused runner.

Do not add profiles/candidates during the night. If a candidate's exact full run
already exists and verifies, reuse it instead of retraining. The two Macs cooperate
by covering different hypotheses; their outputs are **not automatically an ensemble**.

**Important scope limit:** these runs retain the existing joint conservative
selector. Fixed-versus-switching, two-hour, risk-first analysis happens afterward
with the policy-only runner, using the new saved forward predictions. This keeps
model comparison and policy comparison explicit rather than silently modifying
either implemented protocol.

## 5. Shared setup and data handoff

From the root of each matching clone:

```zsh
uv sync --frozen
make test
make lint
uv run ruff check experiments
```

If LightGBM cannot load its OpenMP library on a Mac, install `libomp` using Homebrew
locally. Do not copy another Mac's virtual environment. Match Python **3.11.15**
and the package versions recorded in the source queue plan for this replication;
`uv sync --frozen` alone does not guarantee the same Python patch version.

Transfer a public-data-only handoff containing:

- The agreed source/experiment files and [lockfile](../uv.lock).
- The processed source tables named in `overnight.SOURCES`: training table, hourly
  prices, grid, continuous calendar, archived forecast weather, regional market
  features and their manifest. Preserve the current default table; do not rebuild
  it with optional features into the shared path.
- A **reference copy** of the original queue plan for its source/runtime/code hashes.
  It is provenance, **not a portable runnable plan**.
- For B1/B2, completed reference-job folders containing the completion marker and
  **every CSV named in its report-hash map**. The classifier CSV alone is insufficient.
  Do not transfer incomplete jobs or the live queue lock/status as runnable state.

Use AirDrop, a local network copy or external storage, then verify SHA256. Do not
download another weather grid during the night; these four candidates need no new
network data. Observed-weather augmentation, unsafe renewable vintages and test
labels remain out of model development.

### Ready-to-transfer handoff

The credential-free [data/report archive](../reports/real/overnight/teammate-d1-inputs.tar.gz)
is approximately **9.9 MB** and remains Git-ignored. It contains the seven processed
source files, the original reference plan and the two completed B1/B2 job folders;
no environment files, passwords, API tokens, raw caches or weights are included.

SHA256: `57d5174c87aa11915db2445f146a5c991f290cc9c82b9aa79792ce80b71d18c3`.

Send it separately from the Git push. The teammate should check out the published
commit, place the archive at the clone root, verify its SHA256, and extract **only
in a fresh/non-running clone**:

```zsh
shasum -a 256 teammate-d1-inputs.tar.gz
tar -xzf teammate-d1-inputs.tar.gz
```

The extracted original plan is still reference provenance, not runnable state.
Prepare the local context below, compare its portable fingerprints, then copy the
two extracted completed job folders into the local context:

```zsh
mkdir -p reports/real/overnight/teammate-reference-context/jobs
cp -R reports/real/overnight/20261107-forecast-recency/jobs/current__chain_730_90 \
  reports/real/overnight/teammate-reference-context/jobs/
cp -R reports/real/overnight/20261107-forecast-recency/jobs/regional_prices__chain_730_90 \
  reports/real/overnight/teammate-reference-context/jobs/
```

Do not run these copy commands before local preparation creates its plan/inputs.
Shared source tables may contain public price labels beyond development; the
prepared experiment snapshots and guards still exclude test/refit targets.

## 6. Preparing the 24 GB Mac safely

The original plan records production file sizes/mtimes, packages and source hashes.
Copying it unchanged to another machine often fails correctly. **Never edit the
recorded inventory or checksums to bypass verification.** Prepare a new local
reference context instead:

```zsh
make overnight-prepare \
  RUN_DIR=reports/real/overnight/teammate-reference-context \
  VARIANTS="current regional_prices" \
  PROFILES="chain_730_90"
```

This prepares local development snapshots and records **that Mac's** normal-model
inventory. It does not train or score anything. No grid cache is required for these
two variants. Place the two transferred completed reference-job folders beneath
the new context's `jobs` directory, preserving their original job IDs.

Before consuming them, verify with the repository's existing functions:

```python
# Run through `GRIDSENSE_DATA=real uv run python`, from the receiving clone.
import json
from pathlib import Path
from gridsense.models.overnight import verify_plan, valid_completion

root = Path("reports/real/overnight/teammate-reference-context")
plan = json.loads((root / "plan.json").read_text())
verify_plan(root, plan)
for job in plan["jobs"]:
    assert valid_completion(
        root / "jobs" / job["id"],
        plan["snapshot_sha256"][job["variant"]],
        months=plan["months"], profile=job["profile"], smoke=False,
    )
```

Also compare the new context's `code_sha256`, `runtime_versions`, `source_sha256`
and snapshot hashes against the transferred source-plan fields **before copying
completion reports**. Compare the full experiment-source commit/hashes separately:
the original code fingerprint does not include the standalone experiments folder.
The local production inventory is expected to differ and is deliberately not copied.

The `current` and `regional_prices` snapshot writes were reproduced **byte-for-byte
in memory on the 48 GB Mac** when writing this plan; this is a verified recipe,
not proof the teammate's environment/data already match. If a receiving snapshot
or report hash differs, stop and reconcile inputs/versions. Do not mark it complete
or rewrite the original completion marker. Once reference validation passes,
the dedicated D+1 runner can use this local context without executing its queue.

## 7. Launch commands

These are instructions for the two operators. No new overnight runs were launched
by writing this plan. Run each pair **sequentially**. For each candidate: prepare,
smoke, inspect success, then execute; stop immediately on any failure.

### Your 48 GB Mac — after the original queue finishes

The committed [Mac48 runner](../experiments/train_mac48.zsh) verifies every original
completion before starting, runs both assigned candidates and their policy-only
comparisons sequentially, measures full-run time/memory, and refuses existing outputs.
Run the VS Code task **ML: assigned Mac48 overnight D+1 experiments**, or:

```zsh
caffeinate -i zsh experiments/train_mac48.zsh
```

The equivalent manual training steps are:

```zsh
export GRIDSENSE_DATA=real
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export OMP_NUM_THREADS=1

queue=reports/real/overnight/20261107-forecast-recency
for candidate in forecast_engineered__chain_730_90 weather_extra__default; do
  run_dir="reports/real/overnight/night-mac48-${candidate}"
  uv run python -m experiments.day_ahead_validation --prepare \
    --queue-dir "$queue" --candidate "$candidate" --run-dir "$run_dir" || break
  caffeinate -i uv run python -m experiments.day_ahead_validation \
    --smoke --run-dir "$run_dir" || break
  caffeinate -i uv run python -m experiments.day_ahead_validation \
    --execute --run-dir "$run_dir" || break
done
```

### Teammate's 24 GB Mac — after local reference checks pass

```zsh
export GRIDSENSE_DATA=real
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export OMP_NUM_THREADS=1

queue=reports/real/overnight/teammate-reference-context
for candidate in current__chain_730_90 regional_prices__chain_730_90; do
  run_dir="reports/real/overnight/night-mac24-${candidate}"
  uv run python -m experiments.day_ahead_validation --prepare \
    --queue-dir "$queue" --candidate "$candidate" --run-dir "$run_dir" || break
  caffeinate -i uv run python -m experiments.day_ahead_validation \
    --smoke --run-dir "$run_dir" || break
  caffeinate -i uv run python -m experiments.day_ahead_validation \
    --execute --run-dir "$run_dir" || break
done
```

Every run directory must be new. If a name already exists, inspect its status;
do not delete completed evidence just to make the loop work. Choose a new suffix
only for genuinely new/restarted runs. The `|| break` guards are fail-fast, not a
job scheduler that skips/recovers a failed experiment automatically.

After each verified full run, policy-only stability analysis needs no retraining:

```zsh
GRIDSENSE_DATA=real uv run python -m experiments.day_ahead_policy \
  --source-dir "$run_dir" \
  --run-dir "${run_dir}-policy" \
  --min-hours-per-month 20
```

Run this separately for each completed source. It does not authorize changing the
20-hour benchmark or threshold grid after looking at its scored results.

## 8. Overnight timeline and stop conditions

| Stage | Work |
|---|---|
| Before bed | Finish original queue; freeze/transfer sources; validate both environments and data; run each first smoke |
| First full job | Measure wall time and peak memory (`/usr/bin/time -l` or Activity Monitor); inspect logs for errors, swap and missing coverage |
| Overnight | One sequential two-job workload per Mac; no downloads/pulls/edits to prepared inputs; keep power/lid/ventilation stable |
| Morning | Verify completion/report hashes, exchange reports, compare matched folds and document keep/drop decisions |

**Do not assume training must take all night.** A focused D+1 candidate may finish
much sooner; the earlier dedicated comparison already completed successfully.
Estimate from one measured full run: roughly twice that training time per Mac,
plus preparation/smokes/verification. Stop when the bounded board finishes instead
of launching an unconstrained search to occupy available hardware.

Stop on failed checksum, traceback, unexpected test/refit rows, probability
inconsistency, persistent memory pressure or a missing completion marker. Record
the failure, fix it deliberately, then prepare new inputs if code changed.

## 9. Resume behavior — do not assume every runner is restartable

- **Original `make overnight`:** rerunning the same command verifies completed jobs
  and skips them. The active queue lock prevents a duplicate executor. A partial
  job is restarted; completed verified jobs are preserved. Never resume an obsolete
  fingerprint by rewriting checksums.
- **Dedicated D+1 runner:** locks out duplicate execution but **does not resume
  partial smoke/full outputs**. After a crash, preserve the partial directory and
  prepare a new run directory; do not claim it continues from the previous fold.
- **Policy-only runner:** refuses an existing output directory. It is cheap to rerun
  into a new directory after diagnosing a failure; the source predictions stay fixed.

Both people should update a small shared experiment board with candidate ID,
owner, commit/hash, source/snapshot hashes, run directory, state, start/end time,
peak memory and any failure. Assign a job before starting it to prevent duplicate work.

## 10. Morning handoff and acceptance

Exchange completed reports, predictions, plans and hash maps—not automatically
the latest weights from each laptop. Large ignored run files can travel outside
Git; commit concise verified summaries, code and tests after checks/coordination.
There is no automatic merging of CSV logs or production model versions.

Compare every candidate on the **same forecast keys, quality eligibility, fold
dates and policy constraints**. Keep hourly and whole-slot metrics separate.
Compare identical recency profiles to isolate feature changes; label A2 explicitly
as a recency probe. Include seasonal/LEAR price comparisons from the original queue
where relevant, but do not mix them into slot-policy scores as the same event.

Report at least:

- D+1 cancellation overall and by month, slot counts and active delivery dates.
- Hours offered per month, abstention and safe-opportunity-day capture.
- Probability calibration/Brier and relevant PR-AUC, not accuracy alone.
- Missing/stale-weather coverage and difficult-month failure traces.
- Confidence/evidence limits, source provenance and repeat-development caveats.

**Target for investigation:** at most 10% cancellations with useful volume, using
20 hours/month as a provisional benchmark. Aggregate success is not every-month
success; zero offers are not 100% safe performance. A low-failure score on a small
sample or a post-score chosen threshold is not a deployment guarantee.

If no candidate improves the trade-off, keep the current baseline and investigate
the September failure dates/provenance rather than blindly increasing model size
or running another night of the same sweep. Final model refitting, weather coverage,
auction-confirmation integration and the **single explicitly authorized final-test
evaluation** remain separate work after a justified design is frozen.