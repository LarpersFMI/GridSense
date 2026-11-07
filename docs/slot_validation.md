# Isolated slot-level validation

This experiment compares a **direct whole-slot classifier** with the strongest
verified, completed hourly candidate, using both empirical and conservative policy
selection. It is development research, not a production planner or final evaluation.

Implementation: [experiments/slot_validation.py](../experiments/slot_validation.py).
Regressions: [tests/test_slot_validation.py](../tests/test_slot_validation.py).
The module intentionally lives outside the active queue's protected source tree.
No shared schemas, feature tables, model artifacts, source modules or dependencies
are changed. Existing queue input/source/runtime/artifact fingerprints are checked.

## Four matched arms

| Arm | Predictor | Policy selection |
|---|---|---|
| `hourly_empirical` | Minimum hourly probability, calibrated to whole-slot outcomes | Earlier observed cancellation at or below the canonical target |
| `hourly_conservative` | Same hourly reference | Additional probability, day-support, temporal-stability and day-cluster bound gates |
| `slot_empirical` | LightGBM predicting whether every slot hour clears at or below the canonical near-zero threshold | Same empirical selector |
| `slot_conservative` | Same direct slot classifier | Same conservative selector |

The whole-slot model uses mean/min/max aggregates of **issue-known `f_*` features**,
plus known slot start and length. It does not train on in-sample hourly predictions,
observed future weather, realized prices as features, or the observed augmentation.
All labels/outcome columns are separate from the feature matrix. Overlapping slots
and repeated horizons are date-weighted during fitting and calibration.

Both predictors are calibrated on eligible **earlier calibration-block** slot
outcomes. Therefore the hourly control is a strengthened whole-slot-calibrated
reference, not a reproduction of the old monthly mean-score/combined-price policy.

## Time separation and planning

The existing chronological splitter supplies fitting, early stopping, calibration,
selection and later scoring blocks, with target-label purging between them. Both
models fit only the fitting block, early-stop only on the stopping block, calibrate
only on the calibration block and select thresholds only on the selection block.
June–September development scoring months come from the existing queue/configuration.
The final test and unassigned/refit targets are rejected.

All four arms use identical strict quality eligibility: every slot hour must have
`data_quality == ok` and finite input features. Missing weather remains missing and
ineligible; D+7 will normally have no offers. This quality gate is intentionally
stricter than the original queue proxy and changes the comparison's deployment scope.

Planning replays **daily issue order**, ranking only that issue's slots; no future
month-wide score ranking or realized-label ranking is used. Slot duration/window,
two-slots-per-day and monthly-hours cap come from existing canonical rules. Horizons
are evaluated as separate outlook alternatives; their budgets must not be added
together for an actual customer calendar.

Conservative development settings are explicit in the experiment plan: minimum slot
probability 0.80, at least 15 active delivery dates, a one-sided 90% Wilson lower bound
on all-selected-slots-successful days above `1 - MAX_CANCELLATION`, and acceptable
observed cancellations in both temporal halves of selection. Gates may force complete
abstention. The bound is a **selection heuristic**, not a safety certificate: nearby
dates are dependent, thresholds are selected adaptively, and regime shifts can defeat
earlier observed performance. No-offer results have undefined hit/cancellation rates,
zero utility and explicitly reported missed opportunities, not 100% accuracy.

## Reproduction

Use `uv run python -m experiments.slot_validation`:

1. Prepare with `--prepare --queue-dir <verified queue> --run-dir <new isolated directory>`.
   Optionally pass `--candidate <completed job id>`; otherwise the reference is chosen
   by highest mean-month near-zero PR-AUC, then lowest Brier, among completed jobs.
2. Run `--smoke --run-dir <prepared directory>` for eight boosting rounds and one month.
3. Run `--execute --run-dir <prepared directory>` for the full four-month comparison.

The reference and settings are frozen before the new run. Changing the implementation
requires a new prepared directory. Existing partial/completed output is not overwritten.
Runs use one LightGBM thread to limit contention with the original queue. Smoke report
checksums must verify before full execution. There are no downloads or final-test flags.

Outputs include classification by horizon/quality scope, selected policies, threshold
search evidence, chosen-slot decision traces, a four-arm summary, and checksummed
completion metadata. Inspect cancellation **alongside** hours offered, abstention and
opportunity-day capture. PR-AUC averages are month/horizon summaries, not pooled scores.

## Evidence limits

The candidate is selected from already-explored development scores; these same months
are reused in this targeted follow-up. A chronological protocol prevents within-fold
label leakage but does **not** make this an untouched holdout or prove significance.
While the original queue runs, the best completed reference is provisional; later jobs
may outperform it. Historic source-vintage/publication assumptions remain unresolved.
Freeze a justified design, complete final-refit/forecast-data prerequisites, and obtain
explicit authorization before the single final-test evaluation.

## First completed comparison (2026-11-07)

The isolated [run plan](../reports/real/overnight/20261107-slot-comparison/plan.json)
froze `weather_extra__chain_730_90`, best mean-month near-zero PR-AUC among **14 verified
completed jobs** at preparation. The original queue continued uninterrupted. The new
eight-round smoke and all four **full** June–September folds completed; original code,
runtime, input/snapshot and production-model fingerprints and new report checksums verify.
No final-test marker was created. **270 tests and both repository/experiment lint pass.**

Results: [four-arm summary](../reports/real/overnight/20261107-slot-comparison/full/summary.csv),
[policy scores](../reports/real/overnight/20261107-slot-comparison/full/policy_score.csv),
[selection evidence](../reports/real/overnight/20261107-slot-comparison/full/selection.csv)
and [decision traces](../reports/real/overnight/20261107-slot-comparison/full/decisions.csv).

| Arm | Whole-slot PR-AUC | Eligible Brier | Scored slots | Cancellation | Mean hours/horizon-month | Opportunity-day capture |
|---|---:|---:|---:|---:|---:|---:|
| Hourly + empirical | 0.7836 | 0.1276 | 496 | 21.57% | 37.75 | 48.00% |
| Direct slot + empirical | 0.7498 | 0.1254 | 532 | 20.86% | 39.04 | 52.67% |
| Hourly + conservative | 0.7836 | 0.1276 | 0 | Undefined | 0 | 0% |
| Direct slot + conservative | 0.7498 | 0.1254 | 0 | Undefined | 0 | 0% |

PR-AUC is the mean of eligible month/horizon scores. Brier is candidate-count weighted;
cancel rate is selected-slot weighted. Hours average includes the abstaining D+7 outlook.
Opportunity capture counts dates with a successful offered slot, divided by eligible
dates containing at least one truly safe candidate, separately by horizon/month.
These are **whole-slot** probability metrics and must not be compared numerically with
the earlier hourly near-zero PR-AUC/Brier as if they predicted the same event.

**Verdict: no model/policy promotion.** The direct slot model slightly improves Brier,
cancellation and opportunity capture but worsens ranking. The approximately 0.7-point
cancellation reduction does not meet the canonical 10% target or establish significance.
Both conservative arms abstain in every horizon/month. Earlier conservative candidates
have at most **9 active delivery dates**, below the configured 15-date support requirement;
their best day-hit lower bound is approximately **0.846**, below the required 0.90.
This exposes limited support under the monthly cap and short selection block, not a
successful safety guarantee. Do not weaken those gates using the scored outcomes just
to manufacture offers. A useful next experiment would gather longer, genuinely
out-of-sample earlier policy history and investigate difficult month/regime failures,
then score a frozen conservative design later. All holdout/provenance caveats above apply.