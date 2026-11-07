#!/bin/zsh
# Sequential, isolated D+1 experiments assigned to the 48 GB Mac.
set -euo pipefail
cd "${0:A:h:h}"
export GRIDSENSE_DATA=real
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export OMP_NUM_THREADS=1
export PYTHONUNBUFFERED=1

queue=reports/real/overnight/20261107-forecast-recency
uv run python - <<'PY'
import json
from pathlib import Path
from gridsense.models.overnight import valid_completion, verify_plan

root = Path("reports/real/overnight/20261107-forecast-recency")
plan = json.loads((root / "plan.json").read_text())
state = json.loads((root / "status.json").read_text())
if state.get("state") != "completed":
    raise SystemExit("Original queue has not completed; leave it running and launch this task later.")
verify_plan(root, plan)
for job in plan["jobs"]:
    if not valid_completion(root / "jobs" / job["id"], plan["snapshot_sha256"][job["variant"]],
                            months=plan["months"], profile=job["profile"], smoke=False):
        raise SystemExit(f"Original job is not verified complete: {job['id']}")
print(f"Original queue verified: {len(plan['jobs'])} completed jobs. Starting assigned D+1 work.")
PY

if ! pmset -g batt | grep -q 'AC Power'; then
  print -u2 'WARNING: Mac is on battery. Reconnect AC power before leaving training unattended.'
fi

for candidate in forecast_engineered__chain_730_90 weather_extra__default; do
  run_dir="reports/real/overnight/night-mac48-${candidate}"
  if [[ -e "$run_dir" || -e "${run_dir}-policy" ]]; then
    print -u2 "Run directory already exists: $run_dir. Inspect it; this runner never overwrites results."
    exit 1
  fi
  print "Preparing $candidate"
  uv run python -m experiments.day_ahead_validation --prepare \
    --queue-dir "$queue" --candidate "$candidate" --run-dir "$run_dir"
  uv run python -m experiments.day_ahead_validation --smoke --run-dir "$run_dir"
  /usr/bin/time -l uv run python -m experiments.day_ahead_validation \
    --execute --run-dir "$run_dir"
  uv run python -m experiments.day_ahead_policy --source-dir "$run_dir" \
    --run-dir "${run_dir}-policy" --min-hours-per-month 20
done
print 'Both assigned D+1 experiments and policy-only comparisons completed. No promotion or final test.'