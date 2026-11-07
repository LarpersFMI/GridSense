#!/bin/zsh
# Run one selected development candidate with percentage output and a saved log.
set -euo pipefail
cd "${0:A:h:h}"
export GRIDSENSE_DATA=real
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export OMP_NUM_THREADS=1
export PYTHONUNBUFFERED=1

candidate="${1:-weather_extra__default}"
queue="${2:-reports/real/overnight/reference-context-dev365}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
run_dir="reports/real/overnight/d1-${candidate}-${stamp}-$$"
uv run python -m experiments.day_ahead_validation --prepare \
  --queue-dir "$queue" --candidate "$candidate" --run-dir "$run_dir"
print "Run directory: $run_dir"
print "Progress: $run_dir/progress.json"
print "Saved log: $run_dir/run.log"
print 'Percentages count completed work; they are not remaining-time estimates.'
if ! pmset -g batt | grep -q 'AC Power'; then
  print -u2 'WARNING: reconnect AC power before leaving training unattended.'
fi
uv run python -m experiments.day_ahead_validation --smoke --run-dir "$run_dir" 2>&1 | tee "$run_dir/run.log"
print 'Smoke passed. Full training percentage now restarts at 0%.'
uv run python -m experiments.day_ahead_validation --execute --run-dir "$run_dir" 2>&1 | tee -a "$run_dir/run.log"
uv run python -m experiments.day_ahead_policy --source-dir "$run_dir" \
  --run-dir "${run_dir}-policy" --min-hours-per-month 20 2>&1 | tee -a "$run_dir/run.log"
print "Complete. Training reports: $run_dir/full/summary.csv"
print "Policy comparison: ${run_dir}-policy/summary.csv"