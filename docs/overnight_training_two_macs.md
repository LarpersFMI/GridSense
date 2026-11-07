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
- Historical report/data/runtime/production hashes verify. Integration changes the
  source fingerprint, so old prepared plans are historical and must not be resumed.
- The 48 GB Mac was on battery at the latest check. Reconnect power before leaving
  new training unattended; `caffeinate` does not prevent battery exhaustion.
- Both assigned Mac48 D+1 runs and their policy-only comparisons are **complete**.
  Do not rerun them unchanged just to fill the night.
- The D+1 work is now integrated into **`dev`**, including incoming server/charting,
  drift and prediction-export work. Use the same published `dev` commit on both Macs.
  Integrated verification: **320 tests and lint pass**.
  Ignored input tables and reference reports still require the handoff below.

This is a timestamped status, **not a live progress counter**. Read the
[queue status](../reports/real/overnight/20261107-forecast-recency/status.json)
and corresponding job log for the latest state.

The original D+1 implementation/results remain pinned to `ml/d1-training` commit
`fee98fa`. That branch is historical provenance, not the recommended training branch.
The new `dev` integration does not rewrite any old plan or completion marker. New
experiments need fresh local reference contexts with the integrated fingerprint.

Relevant results/protocols:
[D+1 training](day_ahead_validation.md), [slot comparison](slot_validation.md),
[policy stability](day_ahead_policy.md), and [ML handoff](ml_handoff.md).

### Current reference: extra weather + 365-day D+1 hourly model

Use **`weather_extra__default`** as the development reference. Its fixed dedicated
hourly model with two-hour, risk-first policy selection produced **37 slots, one
failure (2.70% cancellation)** and **18.5 hours/month** across June–September.
Monthly hours: June 0 (abstention), July 12, August 36, September 26. Cancellation
in active months: July 0%, August 0%, September 7.69%.

Results: [training summary](../reports/real/overnight/night-mac48-weather_extra__default/full/summary.csv),
[two-hour policy](../reports/real/overnight/night-mac48-weather_extra__default-policy/summary.csv)
and [monthly decisions](../reports/real/overnight/night-mac48-weather_extra__default-policy/policy_score.csv).

This is **not production promotion**: June abstains, July is below the provisional
20-hour volume benchmark, and 37 slots on 23 dates are insufficient to promise
future safety. The aggregate development target is met, not useful volume in every
month. No final test has been scored. The engineered/730-day conservative candidate
performed worse (18 slots / 5 failures, 27.78% cancellation); do not adopt it.

The reference has already been trained. Compare other feature sets with matching
365-day recency before final refitting; do not blindly repeat the reference run.

These experiment runners currently write prediction/evaluation evidence, not
deployable final model weights. Final D+1 refitting/export is separate work after
feature, model and policy selection is frozen. Ordinary `make train` still uses all
horizons and the normal classifier defaults; it is not the dedicated 365-day D+1
recipe. Do not use it as a shortcut to promote this research candidate.

## 2. Rules before starting

1. **Do not mutate any running experiment.** No pulls, source changes, feature
  rebuilds, dependency updates or production-model replacement in its checkout.
  The original queue and both Mac48 runs are complete; preserve their evidence.
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
| Your M5 / 48 GB | Completed runs: review failure dates, calibration and prepare verified handoff; avoid duplicate training | Keep at least 12 GB free for macOS/editor; investigate sustained worker usage above roughly 30 GB |
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

Do not schedule another 28-job sweep. The completed `weather_extra__default`
D+1 run is now the reference. Prepare fresh integrated-code contexts for new runs.

| Owner | Candidate / state | Question |
|---|---|---|
| 48 GB, A1 complete | `forecast_engineered__chain_730_90`: not preferred | Conservative cancellation 27.78%; no repeat or promotion |
| 48 GB, A2 complete | `weather_extra__default`: current reference | Fixed D+1 hourly two-hour policy cancellation 2.70%; useful volume still incomplete |
| 24 GB, next B1 | `current__default` | Does the simpler feature set retain the D+1 benefit at the same 365-day recency? |
| 24 GB, next B2 | `regional_prices__default` | Do neighbouring prices improve D+1 safety/volume with the same recency? |

Each new dedicated run trains pooled-hourly, D+1-hourly and D+1-slot predictors and
generates seven forward months, followed by four scoring months: **two remaining
candidate runs / 42 predictor fits**, excluding smokes. Policy scoring remains
**D+1 only**. Both new candidates use 365-day near-zero recency to isolate features,
not features and recency simultaneously. The conditional-cheap step is not fitted.

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
- For B1/B2 and the completed default-profile reference, job folders containing the completion marker and
  **every CSV named in its report-hash map**. The classifier CSV alone is insufficient.
  Do not transfer incomplete jobs or the live queue lock/status as runnable state.

Use AirDrop, a local network copy or external storage, then verify SHA256. Do not
download another weather grid during the night; these four candidates need no new
network data. Observed-weather augmentation, unsafe renewable vintages and test
labels remain out of model development.

### Ready-to-transfer handoff

The earlier 9.9 MB archive was for the pinned `ml/d1-training` / 730-day handoff.
Do not use its old runnable plan on integrated `dev`. The updated **dev365 handoff**
contains seven processed sources, an integrated reference plan, completed historical
`current__default`, `weather_extra__default`, `regional_prices__default` reports,
and the completed D+1 reference/policy reports. No credentials, raw caches or weights
are included. The verified [dev365 archive](../reports/real/overnight/teammate-d1-dev365-inputs.tar.gz)
is approximately **14 MB** and remains Git-ignored.

SHA256: `58b06d5d57b948f81b93a61035d1acabc4f629ef64981e1c22f9a8c7ca6e32a3`.

It includes [reference provenance](../reports/real/overnight/reference-context-dev365/provenance.json),
which explicitly identifies copied reports as historical, not new integrated-code
scores. All seven source hashes, three reference-report hash maps, completed D+1
report hashes and **32 tracked Parquet metadata files** verify. Old plans and model
inventories were not rewritten. The original source-machine absolute paths in
historical plans are not suitable as the receiving machine's runnable context.

Send it separately from the Git push. The teammate should check out the published
commit, place the archive at the clone root, verify its SHA256, and extract **only
in a fresh/non-running clone**:

```zsh
shasum -a 256 teammate-d1-dev365-inputs.tar.gz
tar -xzf teammate-d1-dev365-inputs.tar.gz
```

The extracted source-machine plan is still reference provenance, not runnable state.
Prepare the local context below, compare its portable fingerprints, then copy the
two extracted completed job folders into the local context:

```zsh
mkdir -p reports/real/overnight/teammate-reference-context-dev365/jobs
for candidate in current__default weather_extra__default regional_prices__default; do
  cp -R "reports/real/overnight/reference-context-dev365/jobs/${candidate}" \
    reports/real/overnight/teammate-reference-context-dev365/jobs/
done
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
  RUN_DIR=reports/real/overnight/teammate-reference-context-dev365 \
  VARIANTS="current weather_extra regional_prices" \
  PROFILES="default"
```

This prepares local development snapshots and records **that Mac's** normal-model
inventory. It does not train or score anything. No grid cache is required for these
three variants. Place the three transferred completed reference-job folders beneath
the new context's `jobs` directory, preserving their original job IDs.

Before consuming them, verify with the repository's existing functions:

```python
# Run through `GRIDSENSE_DATA=real uv run python`, from the receiving clone.
import json
from pathlib import Path
from gridsense.models.overnight import verify_plan, valid_completion

root = Path("reports/real/overnight/teammate-reference-context-dev365")
plan = json.loads((root / "plan.json").read_text())
verify_plan(root, plan)
for job in plan["jobs"]:
    assert valid_completion(
        root / "jobs" / job["id"],
        plan["snapshot_sha256"][job["variant"]],
        months=plan["months"], profile=job["profile"], smoke=False,
    )
```

Compare the local context's `code_sha256`, `runtime_versions`, `source_sha256` and
snapshot hashes to the transferred **integrated** `reference-context-dev365` plan
before copying reports. Match the published `dev` commit and standalone experiment
hashes separately. The local production inventory is expected to differ; do not copy
or rewrite it. Historical reports were generated under the original implementation;
retain their original completion markers and provenance, never relabel them as new
integrated-code scoring. They identify candidates, not a fresh validation result.

The default control must rebuild exactly, and fresh snapshot hashes must match the
reference context. If receiving data/runtime/code/snapshot/report hashes differ,
stop and reconcile them. Do not edit checksums to force acceptance. Once the local
reference checks pass, the dedicated D+1 runner can consume this context without
executing the original multi-horizon queue again.

The integrated source-machine context is already prepared and verified for all
three default-profile candidates. It performed **no new fitting or scoring**.
The historical report hashes and original data snapshots match exactly; the new
context records the integrated implementation fingerprint independently.

## 7. Launch commands

These are instructions for remaining work; this update launches **no new training**.
For each new candidate: prepare, smoke, inspect success, then execute; stop on failure.

### Your 48 GB Mac — completed training, no automatic rerun

Both assigned runs are complete. Reuse their checksummed results as historical
development evidence. The old [Mac48 runner](../experiments/train_mac48.zsh) is
specific to the original source/queue fingerprint and will correctly refuse it
after integration. Do not run it or rewrite its old plan on current `dev`.

Use the time to examine failed September dates, calibrated probability bins,
missed opportunities and why June/July have low volume. New feature/model changes
require a separately declared bounded experiment, not repeating completed jobs.

### Teammate's 24 GB Mac — after local reference checks pass

```zsh
export GRIDSENSE_DATA=real
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export OMP_NUM_THREADS=1

queue=reports/real/overnight/teammate-reference-context-dev365
for candidate in current__default regional_prices__default; do
  run_dir="reports/real/overnight/night-mac24-dev365-${candidate}"
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
| Before bed | Original queue/Mac48 jobs already done; freeze integrated dev; transfer handoff; validate teammate environment; smoke B1 |
| First full job | Measure wall time and peak memory (`/usr/bin/time -l` or Activity Monitor); inspect logs for errors, swap and missing coverage |
| Overnight | Teammate trains B1/B2 sequentially; 48 GB Mac analyzes existing results; no downloads/pulls/edits under active plans |
| Morning | Verify completion/report hashes, exchange reports, compare matched folds and document keep/drop decisions |

**Do not assume training must take all night.** A focused D+1 candidate may finish
much sooner; the earlier dedicated comparison already completed successfully.
The engineered full D+1 run took about **114 seconds**, with approximately **2.5 GB
maximum resident memory** on the 48 GB Mac. That is measured for that run, not a
guarantee for every candidate/Mac. Allow setup/smoke/verification time and stop
when the bounded board finishes instead
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