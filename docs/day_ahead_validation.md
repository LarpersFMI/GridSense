# D+1 cancellation-target experiment

Focus: forecasts issued at **10:00 Europe/Bucharest for tomorrow**, before its
day-ahead auction result is known. Target: every hour of an offered slot clears
at or below `config.NEAR_ZERO_THRESHOLD_EUR`, with cancellation at or below the
canonical 10% target. The monthly hours budget is a **cap, not a quota**.

Implementation: [experiments/day_ahead_validation.py](../experiments/day_ahead_validation.py).
Regressions: [tests/test_day_ahead_validation.py](../tests/test_day_ahead_validation.py).
This separate experiment does not change the running original queue, prior
slot-comparison source/checksums, production weights, shared schema or data.

## Bounded comparison

- **Pooled hourly reference:** a near-zero classifier trained on all horizons,
  but predictions, slot calibration, policy selection and scoring use only D+1.
- **Dedicated D+1 hourly model:** same configured feature set/parameters, fitted
  only on tomorrow targets. Minimum hourly probability is calibrated to slot truth.
- **Dedicated D+1 whole-slot model:** issue-known feature aggregates with direct
  all-hours-near-zero labels, without in-sample hourly prediction features.

Policy candidates jointly choose predictor, maximum slot length **2, 4 or 6 hours**,
and one of seven predeclared confidence thresholds **0.80–0.99**. The stricter grid
and short-slot candidates are specified before scoring, not searched until a
desirable outcome appears. All arms use the existing slot-quality checks and
causal daily replay; the normal duration/window, daily/monthly caps remain fixed.

The comparison reports a conservative joint policy, an empirical joint-policy
control, and a fixed pooled-hourly 2-hour/0.80-threshold baseline. Joint predictor
selection uses earlier history only; no scoring labels choose a winner or threshold.

## Longer, truly earlier policy history

For prediction month M: fit before M−2, early-stop on M−2, calibrate on M−1 and
predict M. Labels are purged at the next stage's earliest local issue-day start,
with all horizons of a target kept together. No stopping/calibration/score labels
are merged into that month's model fitting. Model features are filtered using
fitting availability only.

March–September development predictions are generated independently, month by
month, with their own earlier fitted model and calibrator. June policy selection
uses March–May forward predictions, July uses April–June, and so on. Entire slot
ends must precede the scored month's earliest issue; no later prediction, label or
monthly score rank enters the selected policy. **Selection expands its evidence
across three months, not across repeated horizons or overlapping slot counts.**

Winter cold starts are explicit: February has no near-zero labels in current data.
A single-class earlier stopping block uses 200 predeclared boosting rounds, while
single-class eligible calibration emits a smoothed constant probability (empty
calibration emits zero). No future positives or observed-weather substitutions are
used to repair sparse history; it may correctly yield no offers in March.

Conservative acceptance requires:

- Earlier observed cancellations at or below 10%.
- At least **15 active delivery dates** and **two active selection months**.
- Observed cancellation at or below 10% in each active selection month.
- A one-sided **90% Wilson lower bound** on all-selected-slots-successful days
  at or above 90%. This is a day-cluster **heuristic**, not a safety certificate:
  adjacent dates remain dependent and adaptive candidate selection is not covered.

Failing evidence means abstention. Do not lower these gates using later outcomes
to force announcements. Daily sequential planning can leave budget unused and never
uses future month-wide scores. D+1 offers use one actual monthly cap, not seven caps.

## Run and read results

Use `uv run python -m experiments.day_ahead_validation`, with a new isolated
`--run-dir` under ignored overnight reports:

1. `--prepare --queue-dir <verified original queue>` freezes inputs/code/settings.
   By default it retains `weather_extra__chain_730_90` from the prior slot comparison;
   an explicit verified `--candidate` is also supported.
2. `--smoke` checks March–June with eight rounds, then June policy selection.
3. `--execute` generates seven monthly forward prediction blocks and four later
   scoring folds. It uses one training thread, locks out duplicate executions and
   verifies the original queue fingerprints and smoke reports.

Reports include chosen policies, candidate acceptance/rejection evidence, raw-hour
and whole-slot classification metrics, cancellation by month, offered hours,
successful/active days, opportunity-day capture, and forward prediction traces.
The summary separates a **nonzero-offer empirical point target** from confidence
and coverage. Neither zero announcements nor a small low-cancellation sample
constitutes a useful, proven deployment result. Deployment approval always remains
false in this research runner.

## Limits

The feature/profile reference and development months have already been explored.
Changing time blocks and the decision rule is another development experiment,
**not a fresh untouched holdout**. PR-AUC for whole-slot events differs from hourly
PR-AUC. Source-vintage/publication assumptions remain unchanged. Honest completion
may find no policy with adequate support. Do not promise 10% on future data from
a selected development score; freeze a justified design, complete final-refit/data
prerequisites, then obtain explicit authorization for the one final-test evaluation.

## First full D+1 result (2026-11-07)

The [frozen plan](../reports/real/overnight/20261107-d1-cancellation-v2/plan.json)
and [full summary](../reports/real/overnight/20261107-d1-cancellation-v2/full/summary.csv)
record seven forward monthly prediction blocks, March–September, followed by
June–September D+1-only policy scoring. Real-data smoke/full report hashes, original
queue code/runtime/source/snapshot/model inventories and dedicated D+1 fitting
checks verify. **288 tests, repository lint and experiment lint pass.** The final
test marker remains absent; no production models are replaced or promoted.

The first preparation encountered the installed LightGBM validation-input API's
list-versus-tuple distinction. That implementation was fixed and covered by a
real-fit regression; the initial partial directory is preserved and obsolete.
The new `20261107-d1-cancellation-v2` plan records the corrected implementation.

| Policy | Scored slots | Failed slots | Cancellation | Mean offered hours/month | Opportunity-day capture |
|---|---:|---:|---:|---:|---:|
| Conservative joint D+1 selection | 38 | 2 | **5.26%** | 19.25 | 28.00% |
| Empirical joint D+1 control | 64 | 10 | 15.63% | 34.75 | 41.33% |
| Fixed pooled-hourly / 2h / 0.80 | 70 | 13 | 18.57% | 35.00 | 42.67% |

The conservative rule's settings and gates were frozen before execution. Each
scoring month's predictor/length/threshold was chosen using its preceding three
forward-predicted months, not that month's labels. It selected the dedicated
hourly model for July/August and the direct slot model for September.

| Scoring month | Conservative chosen predictor | Probability threshold | Slots | Failed | Hours | Cancellation |
|---|---|---:|---:|---:|---:|---:|
| June | Abstain: earlier support fails gates | — | 0 | 0 | 0 | Undefined |
| July | `hourly_d1` | 0.90 | 10 | 0 | 20 | 0% |
| August | `hourly_d1` | 0.90 | 13 | 0 | 26 | 0% |
| September | `slot_d1` | 0.90 | 15 | 2 | 31 | **13.33%** |

**Interpretation: the aggregate development point target is met with nonzero
offers, not yet established as a reliable future or every-month guarantee.**
Only 23 delivery dates are active, June abstains, September exceeds 10%, and 72%
of eligible safe-opportunity days are not captured. The scored day-cluster lower
bound is approximately 0.808, not 0.90. It bounds a different event (all offers on
a date succeed), and must not be presented as a certified slot-cancellation bound.
This supports prioritizing D+1 and conservative selection, but does not approve
deployment or justify tuning on the final test. Future model/policy freeze and
independent final evaluation remain required.

## Later 365-day reference and dev integration

The Mac48 `weather_extra__default` comparison is now complete. Its conservative
joint policy produced 36 slots / one failure (2.78%), while the fixed-hourly,
two-hour risk-first policy-only comparison produced **37 / one (2.70%)**, averaging
**18.5 hours/month**. These are later development results, not a redefinition of
the original 730-day result above. June abstained; July offered only 12 hours.
No policy/model is promoted or guaranteed safe on future data.

The 365-day candidate is the current reference in the
[updated two-Mac plan](overnight_training_two_macs.md). D+1 code is integrated into
`dev`; prior plans remain pinned to their original code and must not be resumed
or have source hashes edited to bypass integration changes. New experiments use
fresh local contexts and matching 365-day controls. Production refitting and the
single authorized final-test evaluation are still separate future work.