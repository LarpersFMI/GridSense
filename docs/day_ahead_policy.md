# D+1 policy stability and useful volume

Implementation: [experiments/day_ahead_policy.py](../experiments/day_ahead_policy.py).
Tests: [tests/test_day_ahead_policy.py](../tests/test_day_ahead_policy.py).

This bounded **policy-only** follow-up reuses the verified saved forward predictions
from the [dedicated D+1 experiment](day_ahead_validation.md). There is no retraining,
new data, production-model replacement, shared-source change or test evaluation.
All earlier D+1/slot runs and the original overnight queue are preserved.

## Comparison specified before execution

- Fixed dedicated D+1 hourly model, adaptive threshold, **2-hour slots only**.
- Switching between dedicated D+1 hourly and whole-slot models, adaptive threshold,
  the same 2-hour slots.
- The preceding volume-first switching policy is retained as a historical control;
  it permits longer slots, so this is not a clean model-architecture causal test.

Both new arms use the same three-month earlier forward prediction history and
conservative gates: 15 active dates, two active months, observed cancellations at
or below 10% in each active month, and the one-sided 90% day-cluster Wilson lower
bound at or above 90%. Additional earlier-history usefulness support requires an
average **20 hours/month**, including inactive history months. This is a provisional
benchmark agreed for investigation, not a proven customer/business requirement.

Eligible thresholds are the existing frozen seven-value grid, 0.80–0.99. Candidate
selection minimizes worst-month cancellation, then pooled cancellation, then
maximizes the day-hit lower bound, and only then offer volume. The fixed hourly
predictor wins complete risk/utility ties to avoid gratuitous switching. No scoring
labels choose predictors, thresholds, lengths or thresholds to add to the search.

Daily issue-order planning, original slot-quality restrictions and canonical
monthly/daily caps are unchanged. Zero offers and low-volume months count against
the utility benchmark. The confidence bound is still a heuristic, not certified
risk control after adaptive search or under serially dependent delivery dates.

## Results (2026-11-07)

Run: [plan](../reports/real/overnight/20261107-d1-policy-stability/plan.json),
[summary](../reports/real/overnight/20261107-d1-policy-stability/summary.csv),
[monthly scores](../reports/real/overnight/20261107-d1-policy-stability/policy_score.csv),
[selection evidence](../reports/real/overnight/20261107-d1-policy-stability/selection.csv).

| Policy | Slots | Failed | Cancellation | Mean hours/month | September cancellation |
|---|---:|---:|---:|---:|---:|
| Fixed D+1 hourly, risk-first, 2h | 35 | 2 | 5.71% | 17.50 | 16.67% |
| Switching D+1, risk-first, 2h | 38 | 2 | 5.26% | 19.00 | 13.33% |
| Previous switching, volume-first | 38 | 2 | 5.26% | 19.25 | 13.33% |

Both new policies abstain in June. July/August use `hourly_d1` at 0.90; in
September the switching arm chooses `slot_d1` at 0.90, based only on earlier
selection evidence. Restricting to the hourly model does **not** improve September;
the previous hypothesis that switching caused the miss is not supported by this
comparison. Changing policy ranking and shortening slots does not remove the two
failed dates. Neither new arm meets average 20 hours/month, and neither meets
both safety and volume in every month. No policy/model is promoted.

## Descriptive risk–volume frontier

The [fixed-threshold table](../reports/real/overnight/20261107-d1-policy-stability/frontier_summary.csv)
and [monthly frontier](../reports/real/overnight/20261107-d1-policy-stability/frontier_by_month.csv)
evaluate only the already-specified threshold grid for each dedicated predictor,
using 2-hour slots. These scores are **descriptive**, not used by the earlier-only
selectors. Choosing a threshold after inspecting them would reuse scoring labels.

At fixed 0.925, the hourly predictor has 42 slots / 0 observed failures and mean
21 hours/month; the direct slot predictor has 48 / 0 and mean 24 hours/month.
Nevertheless, two hourly months and one slot-model month have fewer than 20 hours.
Higher thresholds further shrink volume. **None of the predeclared frontier points
meets at most 10% cancellation and at least 20 offered hours in every scoring month.**
Zero observed failures are not a future guarantee: counts are small, nearby dates
are dependent, the reference/development months were explored, and multiple policies
are being compared. Do not promote fixed 0.925 based on this table alone.

## Reproduction and limits

Use `uv run python -m experiments.day_ahead_policy --source-dir <completed verified
D+1 run> --run-dir <new isolated directory>`. An optional `--min-hours-per-month`
sets the investigation benchmark **before** execution. Existing outputs are not
overwritten; source completion/plan/report hashes and original queue fingerprints
verify before and after the comparison. Output includes a frozen plan, report hashes
and completion status. This module is outside all previous source fingerprints.

Post-run verification: **297 tests pass**, repository and standalone-experiment lint
pass, and output/source/code/report fingerprints verify. The original queue remains
running with its protected inputs and model inventory unchanged. No final-test
evaluation marker exists; no model/policy was promoted.

This is another already-explored development comparison, not an independent
confirmation that risk or utility will generalize. Keep the final test untouched
until the configuration/policy is frozen and evaluation is explicitly authorized.