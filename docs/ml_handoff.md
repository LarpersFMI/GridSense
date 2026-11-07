# ML handoff (price forecasting, ML-P)

## D+1 teammate comparison completed (2026-11-08)

The 24 GB Mac completed `current__default` and `regional_prices__default`
sequentially at `f22a644b778721a1de5aa9a51808deb39b7cceef` with Python 3.11.15.
The [handoff archive](../handoffs/README.md), input snapshots, smoke, full-run and
policy report hashes verified. All three candidates used 365-day recency and
matched forecast keys, eligibility and June–September 2025 development folds.

| Candidate | Two-hour offers | Cancellations | Mean hours per month | June / July / August / September hours |
| --- | ---: | ---: | ---: | --- |
| `weather_extra__default` (reference) | 37 | 1 of 37 (2.70%) | 18.5 | 0 / 12 / 36 / 26 |
| `current__default` | 0 | — | 0 | 0 / 0 / 0 / 0 |
| `regional_prices__default` | 13 | 1 of 13 (7.69%) | 6.5 | 0 / 0 / 0 / 26 |

These are the fixed D+1 hourly risk-first policy results. Keep the extra-weather
candidate as the development reference. It had more offer hours and a lower
cancellation rate than the regional-price candidate, but missed the provisional
20-hour monthly benchmark in June and July. June abstained because no tested
threshold reached 20 hours per month on its preceding selection window. July's
selected 0.925 threshold reached 20 hours per month on its selection window and
offered 12 hours when scored. The current-feature candidate abstained in every
scoring month. The comparison did not promote a model or run another final-test
evaluation. Full predictions, logs and reports are local.

## D+1 integration snapshot (2026-11-07)

The original queue has now **completed all 28 jobs / 112 folds**. Both Mac48 D+1
follow-ups and their policy-only comparisons are also complete. D+1 implementation
`fee98fa` has been merged with current `dev` as `b8c31e0`, including teammate
drift/export and server/charting integration. Integrated **320 tests and lint pass**.
The minimal incoming pipeline lint fixes are recorded as `a1b8393`.
Historical data/runtime/production/report hashes
remain unchanged, but the source fingerprint changes: **do not resume old prepared
plans or rewrite their checksums under this integrated code**.

The current development reference is **`weather_extra__default`**, a dedicated D+1
hourly model with 365-day recency and conservative policy selection. Its two-hour
policy has 37 scored slots / one failure (**2.70% cancellation**) and mean
**18.5 hours/month**. June abstains; July offers 12 hours, August 36, September 26
(7.69% cancellation). This is not useful volume every month or certified future
safety; no production model is promoted and no final-test evaluation was performed.

The [two-Mac plan](overnight_training_two_macs.md) assigned
`current__default` and `regional_prices__default` as the 365-day teammate
comparisons. Their verified results appear above.

The new `reference-context-dev365` locally records integrated code/runtime/source
checks for `current__default`, `weather_extra__default` and
`regional_prices__default`. Imported completion markers are unchanged historical
reports; no new fitting/scoring occurred. The **14 MB dev365 handoff archive** in
the two-Mac plan contains their explicit provenance and completed D+1 evidence.
The 32 tracked Parquets have readable metadata. Original data/model/report hashes
verify, no final-test marker exists, and no model was promoted.

Latest published integration on **2026-11-07**: archived feature engineering committed as
`44bfa50`, explicit chain recency/nested weather calibration as `ea47db5`, and concurrent
upstream `d1f1865` merged as `3e2d370`; the audited integration was published as `0757c7a`.
**246 tests and lint pass; all 29 tracked Parquets are readable.** The default
235,704-row/50-feature table is unchanged. A fresh **28-job / 112-fold** queue is prepared
against that published code. The 730/90 engineered and 365/365 control smokes have zero
probability-order violations; **the full queue has not started**. Local `main`
is still `63bada2`, while `origin/main` has advanced to `2da47ad`; those services have not
been merged into ML. Earlier sections below are historical run records with their original
inputs and model versions. Read the current checklist first, then [price_plan.md](price_plan.md),
[ml_plan.md](ml_plan.md) and the README rules.

## Per-step recency and weather calibration integration (2026-11-07)

The incoming work through `9839df0`, including `a7c9ada`, is now merged as `46f2924`.
The forecast-engineering adaptation was committed as `44bfa50` before that merge.
Observed augmentation remains analysis-only and is not a forecast input. Both review points
are addressed and published; historical results below retain their original model settings.

### Explicit chronological profiles

| Profile | Price half-life | Near-zero step | Conditional-cheap step |
|---|---:|---:|---:|
| `default` | 365 days | 365 days | 365 days |
| `recent` | 180 days | 180 days | 180 days |
| `regularized` | 365 days | 365 days | 365 days |
| `chain_730_90` | 365 days | 730 days | 90 days |

Each [profile](../src/gridsense/models/chronological.py) explicitly supplies both
`step_half_lives`; the runner removes that mapping from LightGBM parameters and copies it
into the classifier. No profile inherits the newly merged conditional 90-day default.
The 730/90 candidate keeps price settings equal to `default` so that contrast isolates
classifier recency. Metadata records price recency and both effective classifier step
half-lives. Profile regression tests verify the exact constructor settings and metadata,
absence of the mapping from LightGBM parameters, and no mutation of the profile definitions.

`a7c9ada` selected the normal classifier's 730/90 defaults using validation early stopping
and month cross-fitting. Those remain development evidence, not a forward-only verdict.
Include `chain_730_90` explicitly in a newly prepared queue to test the choice using separate
earlier fit/stop/calibration/selection stages and later score blocks. No full comparison or
feature promotion is implied by an eight-round smoke.

### Remaining independent-calibration path fixed

[weather_validation.cross_calibrated_predictions](../src/gridsense/models/weather_validation.py)
now calls `classifier.predict_cross_fitted(rows, groups)` instead of calibrating the final
`p_cheap` independently. The conditional step is calibrated only on near-zero-eligible rows;
the output remains `p_near_zero * P(cheap | near_zero)`. Regressions cover Platt/isotonic
nesting, exclusion of all held-month horizons, exclusion of non-near-zero cheap labels and
prediction-index alignment. This helper is still month cross-fit, not forward-chained
validation; old independent classifier artifacts still require retraining.

The nesting and classification-evaluator integration tasks are **done**. Historical pending
notes and Next steps item 4 below are marked accordingly. The normal evaluator already
registers `make evaluate TASK=classify`; this review did not score the final test split.
Both earlier prepared queues are now obsolete because of the merged/new Python checksums;
their snapshots and reports remain untouched. The fresh post-integration queue is
verified in [Prepared run: ready to launch](#prepared-run-ready-to-launch).

**Post-merge validation:** `make test` passed **246 tests**, `make lint` and
`git diff --check` passed. Pylance reports no diagnostics in the two changed runners;
all eight weather-helper call sites match its updated signature. All **29 tracked Parquets**
open, the four incoming changed/new tables decode, and the default **235,704-row / 50-feature**
table rebuilds exactly. Protected training-table/weather hashes are unchanged. No final-test
evaluation was run. The incoming observed-augmentation modules received only the minimal
import/unused-binding lint cleanup needed to restore the repository check; they remain
excluded from forecast features and experiments.

**Concurrent update integrated:** the initial push encountered teammate commit `d1f1865`;
it was merged without force-pushing as `3e2d370`. The full **246-test** suite, lint and
diff check passed again. All **29 tracked Parquets** still open and the default table and
protected source hashes remain unchanged. The shared augmented schema changed upstream;
this does not alter the archived forecast contract or our default training table.

The new augmentation does anchor price memory to an issue date and now uses canonical
`val` splits, but **it still reads observed `weather_hourly` and fabricates issue dates/lead
days from target timestamps**. It has not become an archived-forecast pipeline. Its updated
29,973-row / 37-column artifact has lead-day counts **0:17,486 / 1:12,483 / 2:4**, not the
configured D+1…D+7 forecast keys. Iasi humidity exactly equals observed same-target truth on
all **24,093** non-null development matches. Keep it and its refreshed feature ranking out
of forecasting experiments. This source/schema concern is flagged here for the data owner;
the archived-only `forecast_engineered` candidate remains the safe adaptation of the ideas.

## Forecast engineering from archived inputs (opt-in)

The [new module](../src/gridsense/features/forecast_engineering.py) reuses the incoming
augmentation's **ideas**, not its observed data, delivery-relative price features or
permutation ranking. At the initial adaptation stage no remote changes were merged;
subsequent merges are recorded above. The adaptation itself changed no shared Parquet schema.

- Weather input is the existing `weather_fc` Previous Runs selection for București,
	Constanța, Craiova and Timișoara. Source/horizon/physical/cutoff validation runs before
	engineering. The existing 12-hour publication assumption is **not** upgraded into
	verified operational-vintage evidence. Missing D+7/partial D+6 and early history persist.
- New features: dimensionless solar geometry/cloud potential; heating/cooling degree
	proxies; dry surface-air density and **10 m** wind-power-density proxy; wind U/V vectors.
	Nonlinear operations occur per point before strict equal-point means. These are not
	measured solar irradiance, turbine power or country renewable-generation estimates.
- Thermal bases and price-memory windows come from shared configuration. Extra pressure,
	wind speed or direction absent from the archive remain NaN, not observed-weather fills.
	A separate `f_feng_missing_weather` flag records derived-weather completeness; original
	control columns including `data_quality` remain unchanged.
- Calendar additions are hour/weekday sine/cosine. Price additions are **3/6/24 elapsed
	hours before `issue_ts`**, mean/std only when the whole window is present. No delivery-
	relative windows, future prices or target labels enter these features. UTC windows retain
	distinct DST hours; local dates determine the horizon and configured daily issue cutoff.
- The fixed opt-in set adds up to **51 `f_feng_` columns**. Empty-training features are
	dropped by the existing fit-availability policy. No feature ranking/selection is imported
	from the leaky upstream hourly-price experiment.

`make features FORECAST_ENGINEERED=1` explicitly builds an engineered normal training table,
like the other feature flags; **it was not run against shared data during implementation**.
For safe comparison, choose `VARIANTS="current forecast_engineered"` when preparing a new
overnight run. The [queue integration](../src/gridsense/models/overnight.py) appends features
only to labelled train/validation snapshots, asserts every original control column matches,
and preserves the original six default variants. No new download is required for the core
four-point candidate. This is a candidate, not a demonstrated quality improvement.

Verified in memory on real data: **167,993 labelled development rows** (132,048 train /
35,945 validation), **50 → 101 features**, no empty-training engineered columns and exact
equality of every original control column. Derived-weather completeness is **43.24% train /
84.37% validation**, across all horizons; missing archive coverage is not filled. Shared
training-table and forecast-source hashes match their pre-adaptation values.
**235 tests and lint pass**. The
[31 engineering regressions](../tests/test_forecast_engineering.py) cover observation rejection,
availability/horizon checks, future-price/label perturbations, full-key joins, empty/missing
weather, nonlinear point means, units, price gaps, UTC/DST and explicit CLI opt-in. The queue
also has a regression proving that this extra candidate receives only development rows and
does not enter the six default variants.

**Earlier queue prepared and verified (now obsolete after profile integration):**
[the plan](../reports/real/overnight/20261107-forecast-engineering/plan.json) has seven
candidates (the original six plus `forecast_engineered`) × three profiles (`default`,
`recent`, `regularized`) × four June–September scoring folds: **21 jobs / 84 folds**.
The first job is the engineered candidate so the smoke actually exercises all 101 features.
Its eight-round June smoke passed with **zero nesting violations**; snapshot/report/code/
runtime/source checksums and production-model inventory all verify. The
[completion marker](../reports/real/overnight/20261107-forecast-engineering/smoke/forecast_engineered__default/completed.json)
is explicitly smoke-only, not quality evidence. **The full queue has not started** and no
test-evaluation marker exists. The command
`make overnight RUN_DIR=reports/real/overnight/20261107-forecast-engineering` was the launch
command for that earlier code revision; **do not run this obsolete plan under the newer
profile integration**. Large queue artifacts remain ignored.

**Queue fingerprint boundary:** adding this module/configuration/integration changes Python
checksums. The previous `20261107-validation` snapshots/reports remain untouched, but their
plan cannot execute under this newer code; choose a new directory and smoke-test again.
The incoming-data audit below describes the earlier read-only state, before this adaptation.

## Incoming data audit: origin/dev 9839df0

Read-only audit on **2026-11-07**, after fetching remote refs without merging. The local
implementation remains `bb7a847`; the incoming tip is `9839df054b975a8a236059a9955a4207c21bd449`.
The four incoming commits are `a7c9ada` (per-step classifier recency), `74c0c70` (renewable
source investigation), `dcfb8b3` (observed-weather augmentation) and merge `9839df0`.
All **29 incoming processed Parquets have readable metadata**; all four changed/new
Parquets were decoded and inspected. This is a data-suitability review, not a full incoming
code/test certification. No training, feature rebuild, test-set scoring or customer action
was run. The local default-table hash remains
`e1b8a8345afe81e65b34129ad500187dc4e491a150777f36ca6073cc619b5108`.

### Decision: do not use the augmented table as forecast inputs

The [incoming augmentation builder](https://github.com/LarpersFMI/GridSense/blob/9839df054b975a8a236059a9955a4207c21bd449/src/gridsense/features/feature_augmentation.py#L69-L140)
reads **observed** weather, joins it to prices on delivery timestamp and pivots to one row
per delivery hour. The new table has **29,973 rows / 36 columns**, including 30 selected
features; it has no `issue_ts`, no `horizon_days` and no `f_` features. The model feature
contract therefore cannot consume it directly.

- **Target-hour truth leaks:** `temp_c_oradea` exactly matches the observed temperature at
	the target hour on all **24,093 train/validation delivery rows**. The cloud-derived solar
	proxies and wind/thermal variables likewise originate from target-hour observations,
	not archived forecasts. Do not relabel them as forecasts or simply add `f_` prefixes.
- **Price memory uses the wrong clock:** the
	[lag/window construction](https://github.com/LarpersFMI/GridSense/blob/9839df054b975a8a236059a9955a4207c21bd449/src/gridsense/features/feature_augmentation.py#L159-L181)
	applies row shifts and rolling windows immediately before *delivery*. Train/validation
	checks reproduce those shifts exactly. For longer horizons those prices are not yet
	published at issue time; some D+1 evening windows also include unpublished D+1 prices.
	Recompute price memory relative to the issue date, using the established availability rule.
- **Discontinuous history:** the inner join omits the refit gap and has a **3,626-hour jump**
	before the test period. Row shifts are not elapsed-hour lags across that boundary. No
	test prediction or metric was computed during this inspection.
- **Permutation ranking is not deployment evidence:** the
	[ranking routine](https://github.com/LarpersFMI/GridSense/blob/9839df054b975a8a236059a9955a4207c21bd449/src/gridsense/features/feature_ranking.py#L48-L97)
	fits on train and ranks on validation, but its inputs have the leakage above. The saved
	artifact is only a 444-name list, without scores, source hashes or model provenance.
	Do not reuse this ranking to select production forecast features.
- **Inference is incomplete:** the
	[new-data transform](https://github.com/LarpersFMI/GridSense/blob/9839df054b975a8a236059a9955a4207c21bd449/src/gridsense/features/feature_selection.py#L108-L135)
	does not reproduce the training price lags/windows or all cyclic encodings, and silently
	omits absent selected features. It is not ready to provide the same training/inference matrix.
- The variable called `solar_proxy_wm2` is a **dimensionless 0–1 cloud-adjusted solar-angle
	proxy**, not measured W/m² (train/validation RO maximum approximately 0.935). Keep its
	meaning and units explicit if adapting the idea.

**Reusable ideas, not reusable target-hour values:** solar geometry is known in advance;
wind vectors, heating/cooling degree hours, cloud-adjusted solar proxies and regional
aggregates can be rebuilt from archived forecasts selected at the existing issue cutoff.
Use the full forecast key, `f_` names, train-availability checks and source provenance;
select/freeze features on earlier development blocks, then score later chronological blocks.
Keep the current 50-feature default until that comparison justifies a change.

### Other incoming data and experiment changes

- [Observed weather](../data/processed/weather_hourly.parquet) has **1,019,082 rows** over
	34 locations, with unique `(target_ts_utc, location)` keys. Every timestamp and numeric
	value is unchanged from local HEAD; only split strings changed to lowercase
	`train` / `validation` / `test`. Our splitter uses `val`, so normalize through
	`assign_split`, not the stored spelling. This is not additional forecast coverage.
- [Hungarian calendar](../data/processed/calendar_hungary.parquet) is value-identical.
	[Bulgarian calendar](../data/processed/calendar_bulgaria.parquet) changes 48 holiday flags
	and 24 bridge flags: it removes non-working holidays **2025-12-31 and 2026-01-02** that
	the installed `holidays` package still identifies as non-working days. These dates are
	outside train/validation, so this provides no current training gain; verify the removals
	with the data owner before adopting them.
- The [renewable investigation](https://github.com/LarpersFMI/GridSense/blob/9839df054b975a8a236059a9955a4207c21bd449/docs/renewable_generation_handoff.md)
	adds documentation, not verified issue-known history. Existing renewable inputs still
	have zero eligible train/validation coverage and remain excluded.
- Classifier recency **730 days near-zero / 90 days conditional cheap** is a legitimate
	development candidate, not new data or forward-only confirmation. Its sweep reuses
	validation for early stopping and target-month cross-fitted calibration. Compare it
	explicitly against equal per-step half-lives in the chronological runner before promotion.
	If merged unchanged, its conditional override also makes the current queue's nominal
	365/180-day profiles use 90 days for that step; set and record both half-lives explicitly
	when preparing that new comparison.

### Overnight and documentation boundary

The existing prepared queue remains `smoke_passed`, with no full queue started and no
test-evaluation marker. Its source inventory excludes the observed augmentation and
neighbour calendars, so these new data tables do not improve its current candidates.
However, **merging the incoming Python/schema changes invalidates its code fingerprint**:
prepare a new run and smoke-test it after any such integration. README/handoff-only edits
do not change the implementation fingerprint. No remote changes were merged by this audit.

The README diagram now explicitly separates implemented data/forecasting from the planned
customer-facing agent. Local planner/actions/wording remain stubs; the separate `main`
central-agent is also a placeholder. Generic trigger infrastructure or UI toast messages
are not zero-cost customer notifications. The pitch describes a design goal, not a proven
operational guarantee against expensive free-energy offers.

## Resume checklist: commit and overnight experiments

**Verified before runner implementation:** 139 tests passed, `make lint` and `git diff --check` passed, and all 25
tracked Parquet files have readable metadata. The default training table has **235,704 rows
and 50 features**; an in-memory rebuild matches it exactly, including the detached chain's
pre-download backup. Equality and report input hashes were reasserted after both comparisons.
The test-evaluation marker is absent; normal price/classifier artifact versions are unchanged.

### Extra archived weather (implemented and compared)

- `make weather EXTRA=1` fetches humidity, total precipitation, surface pressure, 10 m wind
  speed and direction for the existing four RO points. GFS rain/snowfall splits are empty.
  Additional values and raw-response hashes are optional columns of the existing forecast
  table, not a shared-schema replacement. Precipitation uses the same preceding-hour
  alignment and conservative 10:00 cutoff selection as radiation. Early history remains NaN.
- `make features WEATHER_EXTRA=1` opts in; wind direction enters as sine/cosine components
  before location averaging. Default features stay unchanged. Features without any training
  values are dropped. Tests cover alignment, merging, angle encoding and empty features.
- Coverage correction after inspecting the completed extraction: all five selected extras
	first appear on **2024-01-20** (precipitation at 11:00 UTC, the other fields at 12:00 UTC).
	The earlier "late February" estimate was incorrect. These are earliest observed selected
	delivery values, not a guarantee of complete intervening history or exact publication time.
- [weather_extra_validation.py](../src/gridsense/models/weather_extra_validation.py) fits
  current versus extras on identical rows, reporting price/low-price MAE, PR-AUC/Brier and
  the 70 h/month slot-budget proxy. It does not save production models or the training table.
- Both downloads and comparisons finished. The old detached chain's equality print was
	not fail-fast; the extras runner now asserts the full control table and verifies its
	file hash is unchanged during fitting. Its verified rerun finished at **19:28**.
- The original grid process loaded a **54-feature** control before the cleanup. Those
	reports are preserved under `reports/real/eval/weather_grid_54_feature_legacy/`, explicitly
	marked historical. A strictly cache-only rerun completed at **19:26**, using the current
	**50-feature** control and 55/63-feature grid variants. No API requests were made.

### Same-row weather comparison results (50-feature control)

All variants use 132,048 labelled train rows / 35,945 validation rows; price and budget
reports use the same 35,932 complete-baseline rows. Values below are rounded development
scores, not chronological confirmation. Only the optional source weather table changed;
the default training table and normal model artifacts did not.

| Variant | Ensemble MAE | Ensemble MAE ≤20 | LightGBM MAE ≤20 | Raw near-zero PR-AUC | Month cross-fit Brier¹ | Classifier slot hit |
|---|---:|---:|---:|---:|---:|---:|
| Current 50 | 20.810 | 32.869 | 35.577 | 0.7639 | 0.0688 | 0.659 |
| +Extras (80) | 20.875 | 33.114 | 34.819 | 0.7725 | 0.0664 | 0.663 |
| +RO grid (55) | 20.850 | 33.177 | 35.620 | 0.7674 | 0.0674 | 0.659 |
| +RO/HU/BG grid (63) | 20.780 | 33.077 | 34.807 | 0.7679 | 0.0683 | 0.654 |

¹These are the existing **leave-one-target-month-out** calibration scores, which use other,
including later, months; they are **not forward-only** scores. Early stopping/CQR/ensemble
weight also reuse validation. The new chronological runner below avoids that reuse.

**Decision: keep every candidate opt-in.** Extras improve classifier ranking and Brier,
but slot hit gains are only 0.4 percentage points and the price ensemble worsens. RO grid
does not improve low-price errors; RO/HU/BG gives a tiny overall ensemble gain while
worsening low-price ensemble MAE and classifier slot hit. This is not a justified default
promotion. Extras are present in ~43% of train / ~84.5% of validation rows averaged across
all seven horizons; D+7 is still missing. Probability nesting remains unresolved: 5,558
current versus 5,564 extras cross-fit rows violate `p_cheap <= p_near_zero`.

**Upstream chain supersedes the independent-classifier nesting limitation.** Commit
`083c9d0` now derives `p_cheap = p_near_zero * P(cheap | near_zero)`, raw and calibrated.
The pre-chain 50-feature reports are preserved under
`reports/real/eval/weather_independent_classifier_50/`; current parent reports are rerun
with the chain and separate conditional-step calibration. Do not silently apply independent
output calibration to the product: each step must be calibrated on its own eligible rows.
Normal local classifier weights predate this change; retrain the default classifier before
using normal `make predict`/classification evaluation. Isolated comparisons and the queue
fit fresh models, so they do not depend on those old artifacts.

The new renewable-generation handoff has zero train/validation coverage under its as-of
policy. It is intentionally **not joined** or used as a missingness signal in these runs;
see [the upstream handoff](renewable_generation_handoff.md).

Post-merge comparisons completed at **19:42 (grid) / 19:44 (extras)** with the nested chain:
**zero cross-fit probability-order violations in every variant**. Near-zero and price
scores in the table above are unchanged. Cheap raw PR-AUC is now 0.6362 current, 0.6364
extras, 0.6292 RO grid and 0.6287 RO/HU/BG grid; month cross-fit cheap Brier is
0.0312 / 0.0308 / 0.0309 / 0.0310 respectively. This does not change the opt-in decision.

Saved current reports: [extras metadata](../reports/real/eval/weather_extra_validation.json),
[extras prices](../reports/real/eval/price_weather_extra_val.csv),
[extras decisions](../reports/real/eval/decision_weather_extra_val.csv),
[grid metadata](../reports/real/eval/weather_grid_validation.json),
[grid prices](../reports/real/eval/price_weather_grid_val.csv) and
[grid decisions](../reports/real/eval/decision_weather_grid_val.csv).

### Before commit/push

1. **Done:** both downloads/comparisons finished; coverage and matching current input hashes
	inspected; default training table equality reasserted. Future downloads share the API
	allowance; do not start concurrent uncached grid jobs.
2. Keep extras/grid **opt-in** pending chronological confirmation. A small gain on the
	repeatedly reused development validation set alone is not sufficient for promotion.
3. Record the actual results and keep/drop rationale here. Commit code, tests, documentation,
	selected processed forecast/manifest changes and completed evaluation reports; exclude
	raw caches, temporary logs and trained weights. A code-only opt-in commit can precede a
	separate results commit; there is no need to finish final model selection before pushing.
4. **Verified:** full tests/lint, default-table equality and tracked Parquet readability
	passed after integrating upstream work. Code/results are committed; push follows the
	readiness documentation update. Processed-data/report backups were preserved before merges.

### Overnight run preparation (separate from final evaluation)

1. **Chronological runner implemented:** separate fitting, early stopping,
	calibration/CQR/ensemble-weight selection and later scoring. For rolling folds, group all
	horizons of a target together and ensure fitting labels were known by the scored issue
	times. Do not use final-test labels. Existing comparisons are development ablations, not
	this forward-only protocol. Bounded predefined parameter/recency profiles are available;
	no Optuna dependency or unconstrained search was added.
2. On that protocol compare the 50-feature control, +extras, +RO grid, +RO/HU/BG grid, and
	regional price-only versus load-only variants. Start with defaults before tuning; only
	shortlist combinations with stable low-price and slot gains by horizon/month. Separately
	assess a no-weather D+7 model. Keep week-ahead excluded without as-issued vintages.
3. Then run a bounded parameter/recency search for shortlisted candidates. Tune a combined
	classifier/P50 slot ranker and announcement thresholds on earlier blocks, and score on
	later blocks. Treat 70 hours as a cap, not a quota: the existing full-budget proxy has
	roughly 34% cancellations. Threshold-only classification slot reports do not enforce the
	same monthly budget; evaluate both constraints together before deployment.
4. Use one sequential, fail-fast, restartable queue with immutable input hashes, explicit
	real mode, run-specific outputs, recorded parameters/seed/code revision and completion
	status. Smoke-test one small job before detaching; keep the Mac powered and awake. Do not
	run `make features` or production `make train` midway through isolated comparisons.
	The older price-ablation entry point requires week-ahead columns and saves a normal price
	artifact, so it is not an isolated overnight task on the current default table.
5. **ML-C chain integrated:** `p_cheap <= p_near_zero` is now enforced by construction;
	the pre-chain 5,558 violations are historical, not a current chain result. Classification
	evaluation and a threshold slot sweep are now registered in
	[evaluate.py](../src/gridsense/models/evaluate.py); older "unregistered" notes below are
	superseded. Do not fix nesting by clipping and retain previous calibration claims.

**Not required for this commit or validation-only overnight runs:** integrating `main`,
new outage/capacity/hydro features, operational exports, final refit, or test evaluation.
Weather extension through the refit/inference period and an explicit refit path are still
needed before final evaluation; normal `make train` only fits the configured training split.
Freeze features/settings/calibration/thresholds and obtain explicit authorization before
the single test evaluation. No test evaluation or real-agent notification was performed.

### Chronological validation and overnight queue

[chronological.py](../src/gridsense/models/chronological.py) scores **June–September 2025**
in four expanding folds. For score month M: fit targets before M−3, early-stop on M−3,
calibrate on M−2, select ensemble/ranker/thresholds on M−1, then score M. Each prior block
is purged at the local start of the next block's earliest issue day, so every label is
known before the next stage's issue time. Day-ahead prices are published before delivery,
not seven days after it. All horizons of a target remain together. Features missing from
fitting history are dropped using that history alone.

The base LightGBMs fit with automatic calibration/CQR disabled. Platt mappings, per-horizon
CQR widening and LEAR residual quantiles fit only the calibration block; ensemble weight
and classifier/price/combined ranker thresholds are selected only on the following selection
block. The price-derived probability uses the fixed LightGBM P50 rather than the later-tuned
ensemble. Score labels never select these settings. The slot proxy combines thresholds with
the **70 h/month cap**, 2–6 h blocks, 09:00–18:00 and at most two per day. It can leave budget
unused or abstain when no selection candidate meets the 10% cancellation target.

This is better-separated **development validation**, not a fresh untouched holdout: these
months have been explored before. Source-vintage assumptions remain unresolved. Monthly
forecast-score ranking is retrospective and not a causal online budget planner. The selected
10% cancellation target is not a guarantee of the later scored cancellation rate.

[overnight.py](../src/gridsense/models/overnight.py) prepares read-only train/validation
snapshots and a checksummed sequential queue. Default candidates: current, extras, RO grid,
RO/HU/BG grid, regional prices/spreads only and regional load only. Default profile uses
365-day recency for price and both classifier steps; optional `recent` uses 180 days for all
three and `regularized` uses 365 days with 15 leaves / 100 minimum child samples.
`chain_730_90` uses price 365 / near-zero 730 / conditional-cheap 90 days. All classifier
step half-lives are explicit, not inherited from normal defaults. All jobs use four
LightGBM threads, recorded seeds/parameters, and
normal model artifacts remain unchanged. No final-test targets enter the snapshots.

Use `make overnight-prepare RUN_DIR=...` for a new directory, optionally
`PROFILES="chain_730_90 default recent regularized"`; `make overnight-smoke RUN_DIR=...` runs only the first
candidate/first fold with eight boosting rounds. It is marked **smoke-only**, not a model
quality result. `make overnight RUN_DIR=...` runs the full queue under macOS `caffeinate`.
Completed jobs resume only when all snapshot/report checksums match. Code or source/model
changes fail fast; prepare a new run rather than changing inputs under a queued experiment.
Large snapshots and per-job outputs under `reports/real/overnight/` are ignored, while code,
tests, documentation and selected completed weather reports are committed.

First-fold limitation: the purged March early-stop block has **only two unique cheap
target hours** (67 near-zero hours). Cheap-step early stopping there is noisy; treat cheap
metrics as secondary and check stability across all four later score months. The April
calibration block has 45 cheap / 83 near-zero hours and both conditional classes, so the
chain's forward calibration is fit-able. No arbitrary minimum-positive threshold was
introduced to hide the difficult fold.

### Prepared run: ready to launch

- Directory: `reports/real/overnight/20261107-forecast-recency/` (local, ignored).
- **28 sequential jobs**: `forecast_engineered`, current, extras, RO grid, RO/HU/BG grid,
	regional prices and regional load × `chain_730_90`, `default`, `recent`, `regularized`.
	Each job scores June, July, August and September: **112 full fold runs** in total.
- [The plan](../reports/real/overnight/20261107-forecast-recency/plan.json) records published
	commit `0757c7a`, code/source/snapshot hashes, Python/package versions, fold boundaries and
	production-artifact inventory. Each of the seven read-only snapshots contains the same
	**167,993 labelled development rows** and preserves every original control column.
	Feature counts in that order are **101 / 50 / 80 / 55 / 63 / 58 / 53**.
- The [first-job engineered 730/90 June smoke](../reports/real/overnight/20261107-forecast-recency/smoke/forecast_engineered__chain_730_90/completed.json)
	**passed** and records price 365 / classifier 730/90, 101 features and zero nesting
	violations. An [additional control June smoke](../reports/real/overnight/20261107-forecast-recency/smoke/current__default/completed.json)
	also passed, recording price 365 / classifier 365/365 and 50 features. Both use eight
	boosting rounds and are **smoke-only**, not quality comparisons. All code/runtime/source/
	model/snapshot/report checks verify. The executor requires the first-job smoke marker
	before full execution.
- Full execution was deliberately **not launched**. Start it with
	`make overnight RUN_DIR=reports/real/overnight/20261107-forecast-recency`; macOS `caffeinate`
	keeps the machine awake for the queue's lifetime. Keep it on power with the lid open.
- Resume with the same command. Do not pull new Python code, rebuild features or replace
	production models after preparation: checksums/inventory will reject a changed environment.
	Prepare a new run directory if those inputs change. Documentation-only commits do not
	change the recorded implementation fingerprint.
- No production artifacts were replaced, no features were promoted, and the test set was
	not evaluated. The normal saved classifier predates the chain and needs default retraining
	before normal prediction/export; the prepared queue fits isolated new models itself.
- Earlier `20261107-validation` and `20261107-forecast-engineering` plans are obsolete under
	the current Python fingerprint. Preserve their snapshots/reports; do not launch them or
	edit checksums to bypass the code guard.

## Roles

- **Me (ML-P, price forecasting):** `features/build.py`, `synthetic/market.py`, `models/{price,lear,baselines(price part),calibrate(conformal),evaluate,metrics(price)}.py`. Training runs on my M5 Max (18 cores, 48 GB).
- **ML-C (low-price classification):** `models/classify.py`, isotonic calibration, classification baselines/metrics, SHAP, `predict.py`. I may train the classifier later.
- **Data engineers:** `src/gridsense/data/` (prices via `entsoe.py` API + `price_snapshot.py` Hugging Face snapshot, weather via Open-Meteo, `price_features.py`, `check_weather_join.py`).
- **Agent/demo:** consume `predictions` (fake version: `make fake-predictions`). Design in [agent_design.md](agent_design.md).

## Key decisions

- Forecast issued 10:00 Romanian time on day D for D+1…D+7; direct forecasting (no recursion).
- Splits: train 2023-01-01→2025-02-28, val 2025-03-01→2025-09-30, test 2026-03-01→2026-10-31 (once, `make evaluate FINAL=1`, guarded by `reports/<mode>/TEST_EVALUATED`). Refit on everything ≤ 2026-02-28 before the test run.
- Labels: `y_price` = hourly mean; `y_near_zero` ≤ 20 €/MWh (primary), `y_cheap` ≤ 0.
- Features: Fourier terms (day-of-year, k=1..3) for cycles; autoregressive price lags as of the issue date; weather by matching lead time; regime features. All `f_` prefixed; models use every `f_` column.
- Wars/politics: not direct features (act through gas/carbon/flows/outages); use in error analysis.
- Fake mode (`GRIDSENSE_DATA=fake`) → `data/fake`, `models/fake`, `reports/fake`; never report fake numbers.

## What exists and works

| Piece | File | Notes |
|---|---|---|
| Fake market data | `synthetic/market.py` | `make fake-data` (~1 s). Weather truth + forecasts by lead, growing solar, weather-driven prices, real holidays, DST. Negative hours ≈1% (2025), 3.6% (2026), midday weekends. |
| Training table | `features/build.py` | `make features` (~1 s): 234,528 rows, 48 features. Leakage + sensitivity + DST tests in `tests/test_features.py`. |
| Seasonal naive, persistence | `models/baselines.py` | Residual quantiles per horizon. |
| LEAR | `models/lear.py` | Lasso per (horizon, hour), 24-h price vectors of D and target−7, asinh, LARS-AIC alpha → coordinate-descent refit, clipped in asinh space, interval from val residuals. |
| LightGBM quantile | `models/price.py` | asinh target, 7 internal quantiles (export P10/P50/P90; `predict_quantiles()` for all), recency weights (half-life 365), early stopping on val, per-horizon conformal (CQR) widening. ~55 s to train. |
| Evaluation | `models/evaluate.py` | `make evaluate` (val) compares all models on the same rows, by horizon; writes `reports/<mode>/eval/price_val.csv`. |
| Train / predict | `models/train.py`, `models/predict.py` | `make train TASK=price|classify`, artifacts in `models/<mode>/<name>/<version>/` + `experiments.csv`. |

**Fake validation results** (pipeline check only):

| Model | MAE | rMAE | Pinball | Coverage | MAE ≤20 €/MWh |
|---|---|---|---|---|---|
| Seasonal naive | 23.7 | 1.00 | 7.48 | 0.77 | 50.6 |
| Persistence | 23.6 | 1.00 (0.91 at D+1) | 7.51 | 0.78 | 52.5 |
| LEAR | **15.7** | **0.66** | **4.89** | 0.79 | **33.7** |
| LightGBM + conformal | 17.4 | 0.74 | 5.57 | 0.80 | 54.4 |

Trees can't extrapolate below training prices → LightGBM weak on low-price hours; LEAR is linear and does better. Fake data is roughly linear, so expect the gap to shrink on real data.

## First real-data run (2026-11-07, price + calendar features only)

Inputs: prices from the pinned snapshot (`make data` with `--source snapshot --end 2026-07-31`, 100% hourly coverage, 491 negative hours), calendar from `python -m gridsense.data.calendar`. No grid or weather table yet: `features/build.py` now skips them when missing (29 features). The Open-Meteo file in `data/raw/` is **archive (observed) weather**, not forecasts issued at 10:00 on D; using it as features would leak, so it is not used.

Validation (all horizons, 35,932 rows):

| Model | MAE | rMAE | Pinball | Coverage | MAE ≤20 €/MWh |
|---|---|---|---|---|---|
| Seasonal naive | 27.6 | 1.00 | 9.74 | 0.81 | 30.7 |
| Persistence | 30.8 | 1.11 (0.89 at D+1) | 10.70 | 0.82 | 38.5 |
| LEAR | 21.1 | 0.76 | 6.81 | 0.79 | 32.8 |
| LightGBM + conformal (level-relative) | 22.8 | 0.83 | 7.46 | 0.80 | 35.3 |
| **Ensemble (0.8 LEAR + 0.2 LightGBM)** | **20.9** | **0.76** | **6.74** | 0.81 | **32.6** |

Changes that got here:
- Snapshot loader expands A03 curves (repeated prices are omitted in the raw points; this caused 847 missing hours).
- Same-hour history features: D-1, and 7-day mean/min/max at the target's local hour.
- LightGBM learns the deviation from the 7-day same-hour mean (`LEVEL_COLUMNS` in `price.py`): MAE 23.8 → 22.8, low-price MAE 46 → 35. Transform and half-life variants (asinh/raw × 180/365/∞) were within ±0.3 MAE of each other.
- `models/ensemble.py`: quantile average, weight picked on val pinball (one parameter, so slightly optimistic on val).

## Validation rerun with week-ahead load (2026-11-07)

Reproducible entry point: `GRIDSENSE_DATA=real uv run python -m gridsense.models.ablate_price`.
It does not change the training table or evaluate test. It refreshes the current 34-feature
LightGBM artifact and writes [ablation results](../reports/real/eval/price_ablation_val.csv),
[input hashes and run metadata](../reports/real/eval/price_ablation_val.json),
[feature availability](../reports/real/eval/price_feature_availability.csv), and the current
[standard validation report](../reports/real/eval/price_val.csv).

Train: 132,048 labelled forecast rows. Validation: 35,945 labelled rows; all variants score
the **same 35,932 rows / 5,134 unique target hours** after dropping missing baseline inputs.
The repeated horizons are not independent observations. Default model settings, all seven
internal LightGBM quantiles, same split dates. No classifier or slot evaluation was run.

| Inputs | Model | MAE €/MWh | rMAE | Pinball | Coverage | MAE ≤20 €/MWh |
|---|---|---:|---:|---:|---:|---:|
| Prices + calendar | Seasonal naive | 27.634 | 1.000 | 9.742 | 81.3% | 30.748 |
| Prices + calendar | LEAR | 21.057 | 0.762 | 6.805 | 79.4% | 32.753 |
| Prices + calendar | LightGBM + CQR | 22.829 | 0.826 | 7.464 | 80.0% | 35.344 |
| Prices + calendar | Ensemble | 20.880 | 0.756 | 6.741 | 81.3% | 32.618 |
| + D−1 actual load | LEAR | 21.081 | 0.763 | 6.812 | 79.4% | 32.984 |
| + D−1 actual load | LightGBM + CQR | 22.994 | 0.832 | 7.497 | 80.0% | 35.304 |
| + D−1 actual load | Ensemble | 20.910 | 0.757 | 6.752 | 81.3% | 32.756 |
| + D−1 load + week-ahead min/max | LEAR | 21.057 | 0.762 | 6.807 | 79.4% | 32.976 |
| + D−1 load + week-ahead min/max | LightGBM + CQR | 22.870 | 0.828 | 7.497 | 80.0% | 34.961 |
| + D−1 load + week-ahead min/max | Ensemble | 20.874 | 0.755 | 6.745 | 81.2% | 32.687 |

**Conclusion: no meaningful overall gain yet.** Adding week-ahead to lagged load reduces
LightGBM MAE by 0.124 €/MWh (0.54%), but its pinball is essentially unchanged and it does
not beat the original prices/calendar model. Ensemble MAE improves only 0.036 €/MWh over
lagged-load-only and 0.007 over prices/calendar; pinball and low-price MAE are slightly worse
than prices/calendar. All variants choose 80% LEAR / 20% LightGBM. Keep prices/calendar as
the reference, rather than treating this tiny difference as an established improvement.
Seasonal naive still has lower MAE on ≤20 €/MWh hours than the ensemble; overall MAE alone
does not establish that we can safely announce zero-cost slots.

| Horizon | Week-ahead availability (val) | Ensemble MAE, prices/calendar | Ensemble MAE, +load +week-ahead |
|---|---:|---:|---:|
| D+1 | 100.0% | 18.169 | 18.198 |
| D+2 | 100.0% | 20.320 | 20.243 |
| D+3 | 85.5% | 21.112 | 21.136 |
| D+4 | 71.0% | 21.367 | 21.346 |
| D+5 | 57.0% | 21.474 | 21.482 |
| D+6 | 43.0% | 21.892 | 21.901 |
| D+7 | 29.0% | 21.827 | 21.810 |

**Limitations:** week-ahead results are exploratory, not a proven leakage-free backtest.
The builder ignores `updated_at_utc` and assumes availability from Saturday before the
target week. Historical updates were re-stamped in the 2025 migration, and the parser keeps
the latest revision per delivery day. A calendar mask cannot prove that this revision was
known at issue time. Preserve original publication timestamps and forecast versions, then
use an as-of join; otherwise document the assumption and retain the no-week-ahead baseline.
The actual-load archive is also a revised historical source, not a real-time vintage archive.
Early stopping, residual/conformal calibration, and ensemble weight selection reuse validation;
coverage here is a tuning score, not an independent guarantee. All-empty solar/wind features
were retained in the load variants to match current training; changing feature count also
changes LightGBM's feature subsampling. Confirm candidate gains with rolling/blocked validation
before final test. The test marker was absent and remains absent.

## Classification baselines pulled (2026-11-07, before weather integration)

Commit `3c7ab1c` adds `Climatology` and `SolarRule` in
[models/baselines.py](../src/gridsense/models/baselines.py), with four baseline tests.
Climatology fits month × weekday × local hour frequencies on **unique training target hours**,
with shrinkage toward month × hour rates. It does not use validation labels or weather.
SolarRule uses forecast mean irradiance ≥500 W/m² on weekends/holidays, with train-fitted
probabilities for whether the rule fires.

Real validation uses all 35,945 labelled forecast rows / 5,135 unique hours (unlike price
evaluation, classification does not need to drop missing seasonal-naive price inputs).
Train has 1,395 unique ≤20 €/MWh hours and 263 unique ≤0 €/MWh hours. Validation has 782
and 295 respectively. Their frequencies increase from 7.4%→15.2% and 1.4%→5.7%, although
the validation period is intentionally spring/summer, so this is not a season-matched drift test.

| Model | Label | PR-AUC (average precision) | Precision@k | Brier |
|---|---|---:|---:|---:|
| Climatology | ≤20 €/MWh | 0.7051 | 0.6166 | 0.08550 |
| Climatology | ≤0 €/MWh | 0.5896 | 0.6048 | 0.04163 |
| LightGBM, uncalibrated | ≤20 €/MWh | 0.7463 | 0.6666 | 0.07785 |
| LightGBM, uncalibrated | ≤0 €/MWh | 0.6003 | 0.6320 | 0.04270 |

Classifier retrained with `GRIDSENSE_DATA=real uv run python -m gridsense.models.train --task classify`;
artifact `20261107T144233-3c7ab1c`, 34 features, 197 rounds for near-zero and 377 for cheap.
Metrics are logged in [experiments.csv](../reports/real/experiments.csv). Predictions were
checked on the same full validation rows as climatology; every probability is finite and
within [0,1]. **Near-zero classification beats climatology on all three metrics.** Cheap
classification ranks slightly better but has worse Brier, so probability quality is not yet
better. Isotonic calibration and independent/blocked validation are still needed. Early stopping
uses this validation set; these are development scores, not untouched holdout scores. The
week-ahead provenance limitations above also apply to this 34-feature classifier. No classifier
feature ablation, slot evaluation, or test evaluation was performed.

| Horizon | Climatology PR-AUC ≤20 | LightGBM PR-AUC ≤20 | Climatology PR-AUC ≤0 | LightGBM PR-AUC ≤0 |
|---|---:|---:|---:|---:|
| D+1 | 0.7051 | 0.7639 | 0.5896 | 0.6033 |
| D+2 | 0.7051 | 0.7596 | 0.5896 | 0.6047 |
| D+3 | 0.7051 | 0.7504 | 0.5896 | 0.6054 |
| D+4 | 0.7051 | 0.7435 | 0.5896 | 0.6048 |
| D+5 | 0.7051 | 0.7410 | 0.5896 | 0.5957 |
| D+6 | 0.7051 | 0.7371 | 0.5896 | 0.5964 |
| D+7 | 0.7051 | 0.7305 | 0.5896 | 0.6051 |

`k` equals the positive count among scored forecast rows (R-precision), not the customer's
notification budget; tied scores use the metric helper's sorting and can make precision@k
order-sensitive. The seven repeated horizons are not independent target observations.

**At this run, SolarRule was unavailable on real data:** `f_ghi_mean` and the `weather_fc` table were missing.
Do not add a dummy zero irradiance column or observed target weather to make it run. It can
only be compared once valid archived forecasts cover the same train/validation rows. The
pulled class treats row-level NaN irradiance as a non-firing rule; report forecast coverage
explicitly when evaluating it later.

**Historical integration task — now done:** at this run the evaluator registered only price
and isotonic was a stub. [models/evaluate.py](../src/gridsense/models/evaluate.py) now registers
`make evaluate TASK=classify`, with common classifier/baseline scoring and calibrated reports.
The nested chain fixes probability ordering. The uncalibrated values above remain historical
results, not scores of the newer implementation.

## Archived weather integrated (2026-11-07)

`make weather` now downloads **GFS Global** Previous Runs forecasts for Bucharest, Constanța,
Craiova and Timișoara. Then run `make features train`, `make evaluate TASK=price`, and
`GRIDSENSE_DATA=real uv run python -m gridsense.models.weather_validation` for the matched-row
weather/no-weather comparison. The weather downloader defaults to the configured train start
through validation end, **not test**. Its CLI supports explicit `--start`, `--end`, and
`--locations`; extend to the final refit/inference period before using those dates operationally.

The [downloader](../src/gridsense/data/weather.py) preserves the existing `WEATHER_FC` contract;
additional source/model/offset/initialization-bound/retrieval/raw-hash columns provide provenance.
Raw monthly multi-location responses are cached locally and reused. There are 674,660 forecast
rows / 24,095 target UTC hours × 7 horizons × 4 locations. **No observed weather, noise-added
reanalysis, or ECMWF hindcast was used.** The training table now has **54 features, 52 populated
somewhere in train**: the previous 34 plus 16 location-specific weather features and 4 means.

### Availability and cutoff policy

The [Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) supplies fixed lead-time
chunks, not one archived run frozen at D 10:00. Naively selecting `_previous_day{horizon}` can
leak the issue afternoon's model runs. For every delivery interval [t,t+1h), we select:

$$n = \left\lceil \frac{t+1\text{h} - \text{issue\_ts} + 12\text{h}}{24\text{h}} \right\rceil$$

Use only offsets 1…7. The latest possible initialization plus the assumed 12-hour publication
buffer must be ≤ issue time. **The buffer is conservative but not historically verified**:
Open-Meteo does not return original release timestamps. This integration is a documented
as-of approximation, not a certified exact operational-vintage backtest. Exact full D+1…D+7
coverage requires an archive such as raw operational NOAA GFS, with initialization, forecast
step, and contemporaneous object/publication evidence. Do not use Open-Meteo's older ECMWF
[single-run archive](https://open-meteo.com/en/docs/single-runs-api) as a substitute without
checking provenance: it explicitly includes Cycle 49R1 hindcasts.

Radiation at API timestamp t+1 is the preceding-hour mean and is aligned to the delivery
interval [t,t+1); cloud, wind and temperature use timestamp t. One extra response day protects
end-of-month alignment. Unsupported offsets, absent history and impossible physical values
remain NaN; no forward-fill from newer runs or observed weather. The archive contained 101%
cloud values: 176 selected impossible values were masked, retaining original responses.

Earliest non-null target dates in this extraction: temperature from the requested start;
radiation/cloud from **2024-01-20**, 100 m wind from **2024-02-17**. These are observed coverage,
not a promise that every intervening hour/variable is complete.

| Validation horizon | Mean weather feature availability |
|---|---:|
| D+1…D+5 | 100% |
| D+6 | 91.8% |
| D+7 | 0% |

All location-specific fields must be present for `data_quality="ok"`; partial locations,
unsupported horizons and dates beyond the downloaded range get `missing_weather`. The
existing prediction builder passes this optional flag through without a schema change.
Location means can still use the remaining locations; the flag prevents that aggregation
from hiding partial input quality.

### Matched-row validation results

Price models score the same 35,932 validation rows. Classification scores all 35,945 labelled
validation rows. These are development scores: early stopping and price conformal calibration
reuse validation, classification is not isotonic-calibrated, and the publication assumptions
for weather/week-ahead remain unresolved. Test was not evaluated.

| Price model / inputs | MAE €/MWh | Pinball | Coverage | MAE ≤20 €/MWh |
|---|---:|---:|---:|---:|
| LightGBM, previous 34 features | 22.870 | 7.497 | 80.0% | 34.961 |
| LightGBM, +weather (54 features) | 22.573 | 7.381 | 80.0% | 34.626 |
| Ensemble, previous 34 features | 20.874 | 6.745 | 81.2% | 32.687 |
| Ensemble, +weather | 20.773 | 6.707 | 81.9% | 32.396 |

Weather reduces LightGBM MAE by **1.3%** and pinball by **1.5%**. The weather-feature LEAR
alone worsens (MAE 21.057→21.326); the ensemble nevertheless improves modestly and chooses
70% LEAR / 30% LightGBM, rather than 80% / 20%. D+7 has no weather signal and the shared
LightGBM's D+7 MAE slightly worsens; consider retaining a separate no-weather long-horizon
model after blocked validation, not assuming every horizon benefits.

| Classifier inputs | Label | PR-AUC | Precision@k | Brier |
|---|---|---:|---:|---:|
| Previous 34 features | ≤20 €/MWh | 0.7463 | 0.6666 | 0.07785 |
| +Weather | ≤20 €/MWh | 0.7602 | 0.6794 | 0.07792 |
| Previous 34 features | ≤0 €/MWh | 0.6003 | 0.6320 | 0.04270 |
| +Weather | ≤0 €/MWh | 0.6274 | 0.6416 | 0.04167 |

Ranking improves for both labels. Near-zero Brier is essentially unchanged/slightly worse;
do not describe this as improved calibration or ready-to-announce slots.

SolarRule can now be scored, **only on the same 30,388 complete-radiation rows for every
comparator** (missing D+7/late D+6 excluded). Train-fitted default threshold is 500 W/m².

| Model on complete-radiation validation | PR-AUC ≤20 | PR-AUC ≤0 |
|---|---:|---:|
| Climatology | 0.7051 | 0.5896 |
| LightGBM, no weather | 0.7489 | 0.5999 |
| LightGBM, +weather | 0.7669 | 0.6309 |
| SolarRule | 0.4279 | 0.3701 |

The two-outcome solar rule is weaker at ranking than climatology/LightGBM. Its training
implementation treats missing irradiance as non-firing; this caveat is recorded, and its
validation scores are not compared against models scored on a larger/different population.

Artifacts: classifier `20261107T145655-3c7ab1c`, quantiles `20261107T145745-3c7ab1c`. Saved outputs:
[weather/no-weather price comparison](../reports/real/eval/price_weather_val.csv),
[classification + solar comparison](../reports/real/eval/classify_weather_val.csv),
[coverage](../reports/real/eval/weather_feature_availability.csv), and
[input hashes/provenance](../reports/real/eval/weather_validation.json).
**Historical evaluator gap — now done:** `make evaluate TASK=classify` is registered. The
dedicated weather runner produced the historical comparison above; its remaining cross-fit
helper now delegates to the nested classifier rather than calibrating the cheap product.

## Latest dev/main integration (2026-11-07)

Both remote tips were fetched and matched against local branch refs: `dev` at `4d73902`,
`main` at `63bada2`. The local ML/weather work was reapplied and the backup stash retained;
no commit, push, or merge of the TypeScript services into dev was made in this integration.

### Useful dev changes: calibration

Commit `4d73902` implements Platt scaling by default, isotonic as an option, calibration
cross-fit by validation month, and reliability tables/plots. Retrained the existing 54-feature
classifier using the same train/validation rows, producing artifact `20261107T152133-4d73902`.
The quantile model remains `20261107T145745-3c7ab1c` and its previous price scores are unchanged.

The [weather validation runner](../src/gridsense/models/weather_validation.py) now explicitly
requests **raw** predictions for the original weather/no-weather comparison. Otherwise the
new default would misleadingly compare a val-fitted calibrated model against old raw models.
Calibration scores use leave-one-target-month-out mapping; every horizon for a target stays
in the same held-out month. Deployment predictions use the model's all-validation calibrators.

| Label, same 35,945 validation rows | Raw PR-AUC | Cross-fit Platt PR-AUC | Raw Brier | Cross-fit Platt Brier |
|---|---:|---:|---:|---:|
| ≤20 €/MWh | 0.7602 | 0.7425 | 0.07792 | **0.06902** |
| ≤0 €/MWh | 0.6274 | 0.5992 | 0.04167 | **0.03229** |

Brier improves by about 11.4% and 22.5% respectively. Pooled ranking drops because different
held-out months get different mappings; a single positive-slope Platt mapping preserves rank
within its sample. This is useful probability-quality development evidence, **not untouched
forecast validation**: base-model early stopping still used validation, and month cross-fit
includes other, later months rather than forward-only folds. Do not select announcement
thresholds based on all-validation in-sample calibration scores.

Updated [classification report](../reports/real/eval/classify_weather_val.csv),
[experiment log](../reports/real/experiments.csv) and
[protocol/provenance](../reports/real/eval/weather_validation.json); generated
[near-zero reliability plot](../reports/real/eval/reliability_p_near_zero.png) and
[cheap reliability plot](../reports/real/eval/reliability_p_cheap.png).
The normal prediction builder was smoke-tested on a validation issue: 168 rows, finite
probabilities/price medians, with missing-weather flags preserved. No test evaluation or
server notification was sent.

**Flag to ML-C before deployment:** independently trained/calibrated labels are not constrained
to the logical ordering P(price≤0) ≤ P(price≤20). The calibrated validation artifact violates
that ordering on 3,269 forecast rows (9.1%). Coordinate a constrained prediction/calibration
design and revalidate it; do not silently clip probabilities and retain the old calibration
claims. The ranking/Brier improvements do not remove this deployment issue.

### Useful dev changes: dataset contracts repaired

Commit `176caf3` contributes 1,019,082 observed-weather rows and Romanian/Hungarian/Bulgarian/
Moldovan calendars. Its shared schema changes had replaced the forecast-weather columns and
made country metadata mandatory for the single-country ML calendar, breaking existing
forecast parsers and joins. The regression was reproduced and repaired in
[schemas.py](../src/gridsense/schemas.py):

- `WEATHER_FC` retains issue/target/lead/location and irradiance/cloud/100m wind/temperature.
- `WEATHER_HOURLY` registers the observed table separately. Its old fabricated issue/lead
	extras are not forecast publication evidence; the updated generator no longer creates them.
- `CALENDAR` retains the existing continuous Romanian ML contract; `COUNTRY_CALENDAR`
	registers the enriched exports independently, without requiring their extra fields in ML.
- [Weather generator](../data/interim/generate_weather_parquet.py) and
	[calendar generator](../data/interim/generate_calendar_parquets.py) now import the installed
	`gridsense` package and use the correct separate contracts. Collected Parquets were not
	deleted or rewritten by this repair.
- Feature building rejects observed-weather columns, fabricated zero-day leads, non-Romanian
	target calendars and duplicate target UTC hours. Regression tests cover these cases and
	confirm observed-data conversion cannot overwrite archived forecasts.

All seven forecast/observed/calendar tables can now be read through `gridsense.io`.
Observed weather can help error analysis or release-safe historical lags, **not target-hour
weather training**. The country calendars provide safe holiday information for future
neighbour features, but their exports omit unassigned/refit periods and the target extension,
and can contain partial foreign-country boundary days. They were not substituted for the
continuous Romanian calendar or added as model features in this run.

### Main services: useful handoff, not merged or run

`main` adds the server/watchdog, dataset triggers, replay tooling and run/dataset update
reporting. They do not add ML training inputs or a better forecaster. Inspecting their
contracts identified the work needed before attaching real predictions:

- The Parquet timestamp, horizon, probability and quantile columns match. Extra
	`model_name`/`model_version` columns are accepted by the loose row schema and passed
	through; **do not remove ML provenance fields**.
- `main` accepts `data_quality` only as `ok`, `degraded`, or `failed`. Our `missing_weather`
	must map to `degraded` at an explicit export boundary (retain the detailed reason), or the
	teams must agree to expand the server enum. No silent relabelling to `ok`.
- The watchdog reads the shared `DATASET_DIR` files, not an arbitrary per-run path in the
	report body. Run history must be appended and atomically replaced before announcing the
	update; the current ML `predict` command replaces a selected batch rather than maintaining
	the append-only history the watchdog uses for its watermarks.
- The reporter on `main` can send a run notification with issue timestamp, model version,
	row count, and file path after a successful export. It was not invoked here. Agree on
	shared/container paths and the quality mapping before connecting real outputs.
- `central-agent` remains a placeholder in the inspected main snapshot. Trigger hits alone
	are not completed customer-facing actions.

Next integration should coordinate those contracts with the agent owner. For now the main
services stay isolated and the existing synthetic replay is distinct from ML validation.

## Latest pull before committing ML/weather work (2026-11-07)

Fast-forwarded `dev` to `2d63586`, including `a47852c`'s validated File Library tables.
Kept the **upstream** calendar, prices/native prices, price-quality report, grid and regional
tables when resolving the stash conflicts; did not replace the new data with the older
snapshot copies. Both pre-pull backup stashes remain available.

- RO/HU/BG prices now each have **33,600 complete hours through 2026-10-31**, with no missing
	native price intervals in the incoming reports. The Aug–Oct price-label gap is resolved.
- Regional tables are now regenerated from File Library data rather than the stale snapshot.
	They still need a controlled regional-feature integration/ablation before use by ML.
- Shared grid coverage extends through October: 33,220 populated load hours, 8,171 solar
	hours, and 7,268 wind hours after the upstream source-update cutoff mask. Early generation
	measurements remain unavailable under that mask; do not infer full train-history coverage.
- Rebuilt tracked `training_table` using those upstream tables plus local archived weather
	and week-ahead data: **235,704 rows, 54 features**. Compared all train/validation keys,
	labels and feature values with the pre-pull backup: no numerical changes. The recorded
	validation comparisons remain applicable to those rows; their original full-input hashes
	and timestamps are preserved rather than rewritten as if the runs were new.
- Resolved forecast/observed schema naming using `WEATHER_ARCHIVED_FC = WEATHER_FC` for
	compatibility with the new weather join checks; observed data uses `WEATHER_HOURLY`.
	Core calendar building now works without the ignored raw holiday CSV, while retaining
	country/working-holiday/split metadata when available.

Raw forecasts, File Library inputs and trained model weights remain ignored. The tracked
training table is rebuilt derived data; reproducing its weather/week-ahead features needs
the documented downloads. No new test evaluation, tuning on test, or server notification
was performed. This update supersedes the earlier inventory's July-only/stale-regional status.

## HU/BG regional-feature ablation (2026-11-07, local experiment)

Implemented an **opt-in** ML join in [features/regional.py](../src/gridsense/features/regional.py).
`make features REGIONAL=1` verifies the existing regional Parquet's tracked manifest checksum
and joins its 11 lag/spread features on issue/target/horizon. Default `make features` remains
unchanged. No shared schema or source-table columns were changed. The join rejects duplicate
or invalid forecast keys, unexpected feature columns and overlaps with existing ML features;
it preserves all rows, original indices, labels and baseline features. Missing inputs are
retained with `missing_regional` (combined with `missing_weather` when needed).

Reproduce the comparison with
`GRIDSENSE_DATA=real uv run python -m gridsense.models.regional_validation`.
It fits **both variants from scratch**, 54 current features versus 65 with the regional input,
using the same 132,048 train rows / 35,945 validation rows. Price scores use the same 35,932
complete-baseline rows. All train/validation keys matched the regional table; some lag inputs
remain missing for DST/early-history hours. The checksum matches the File Library manifest.

| Price model | Current MAE | +Regional MAE | Current pinball | +Regional pinball | Current MAE ≤20 | +Regional MAE ≤20 |
|---|---:|---:|---:|---:|---:|---:|
| LEAR | 21.322 | 21.257 | 6.869 | 6.856 | 32.934 | 32.046 |
| LightGBM + CQR | 22.573 | 22.627 | 7.381 | 7.389 | 34.626 | 34.734 |
| Ensemble | 20.770 | 20.728 | 6.706 | 6.694 | 32.391 | 31.859 |

Both ensembles select 70% LEAR / 30% LightGBM. Overall ensemble MAE improves only **0.2%**,
pinball about 0.17%, and low-price-hour MAE about 1.6%. LightGBM price regression alone
slightly worsens. This is not evidence of a large or independently significant benefit.

| Horizon | Current ensemble MAE | +Regional ensemble MAE |
|---|---:|---:|
| D+1 | 18.002 | 17.865 |
| D+2 | 19.880 | 19.811 |
| D+3 | 20.596 | 20.536 |
| D+4 | 21.427 | 21.368 |
| D+5 | 21.670 | 21.886 |
| D+6 | 22.054 | 22.086 |
| D+7 | 21.759 | 21.547 |

| Classifier score | Label | Current PR-AUC | +Regional PR-AUC | Current Brier | +Regional Brier |
|---|---|---:|---:|---:|---:|
| Raw | ≤20 €/MWh | 0.7602 | 0.7624 | 0.0779 | 0.0772 |
| Raw | ≤0 €/MWh | 0.6274 | 0.6292 | 0.0417 | 0.0403 |
| Platt, month cross-fit | ≤20 €/MWh | 0.7425 | 0.7456 | 0.0690 | 0.0688 |
| Platt, month cross-fit | ≤0 €/MWh | 0.5992 | 0.6048 | 0.0323 | 0.0321 |

Classification changes are also small. Near-zero raw ranking improves at each horizon, but
cheap-hour precision@k slightly worsens. Cross-fitted probability nesting violations remain:
3,248 current rows versus 3,427 regional rows have `p_cheap > p_near_zero`. This experiment
does not fix the existing independent-label calibration/deployment issue.

**Decision:** keep the current 54-feature defaults/production artifacts. Keep regional
features available for further validation, not automatically promoted. Next isolate price
and load subsets and confirm candidate gains on chronological blocks before choosing a
per-horizon model/feature policy. D+5/D+6 price performance does not improve here.

Source-vintage and archived-weather/week-ahead publication assumptions remain unchanged.
Early stopping, price interval calibration and ensemble weighting still reuse validation;
classifier calibration is cross-fitted by target month, not forward-only validation. Multiple
horizons repeat target labels. The future-perturbation/sensitivity tests prove lag logic and
join correctness, not that every historical source revision was available at issue time.

Experiment models are isolated under `models/real/regional_experiment/20261107T153923-15303cd/`.
The normal classifier/price artifact versions and tracked training table are unchanged;
the runner verified the original training-table hash. No test evaluation, commit, push or
agent notification was performed. Saved reports:
[price comparison](../reports/real/eval/price_regional_val.csv),
[classification comparison](../reports/real/eval/classify_regional_val.csv),
[regional input coverage](../reports/real/eval/regional_feature_availability.csv),
[P50 model gain importance](../reports/real/eval/regional_price_importance.csv), and
[run/provenance metadata](../reports/real/eval/regional_validation.json).

## Validation error decomposition and budget metrics (2026-11-07)

`GRIDSENSE_DATA=real uv run python -m gridsense.models.error_analysis` refits the default
54-feature models (no artifacts replaced; ensemble horizon MAEs reproduce the regional run's
"current" column exactly) and writes [error breakdown](../reports/real/eval/error_breakdown_val.csv),
[decision metrics](../reports/real/eval/decision_metrics_val.csv),
[classification scores](../reports/real/eval/error_analysis_classify_val.csv) and
[metadata](../reports/real/eval/error_analysis_val.json). Same 35,932 price rows.

| Actual price band | Rows | Ensemble MAE | Seasonal naive MAE | Ensemble bias | Share of ensemble abs. error | P10–P90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| ≤0 | 2,065 | 26.7 | 27.8 | +14.3 | 7.4% | 77.8% |
| 0–20 | 3,409 | 35.8 | 32.5 | +32.2 | 16.4% | 66.8% |
| 20–60 | 2,814 | 23.2 | 33.1 | +15.9 | 8.7% | 77.3% |
| 60–120 | 19,076 | 13.7 | 21.1 | −1.6 | 35.1% | 87.8% |
| 120–200 | 7,350 | 21.9 | 31.3 | −1.9 | 21.6% | 80.9% |
| >200 | 1,218 | 66.2 | 81.7 | −55.9 | 10.8% | 54.4% |

- **Low hours are systematically over-forecast** (bias +14 to +32 €/MWh, P10–P90 coverage 67% in
	0–20). Seasonal naive beats the ensemble in the 0–20 band. **Spikes above 200 are under-forecast**
	(coverage 54%). Overall MAE is dominated by ordinary 60–200 hours (57% of error), which barely
	affect announcements; do not rank features by overall MAE.
- By local hour, evening 20:00–21:00 has the largest MAE (~40) and midday 11:00–17:00 ~25–28 with
	positive bias. March and September (transition months) are worst (~23.5); weekends are easiest.
- Horizon decay is mild for the ensemble (18.0 at D+1 → ~21.7 at D+5–D+7).

Announcement proxy: per horizon and validation month, the 70 h/month budget is filled with
2–6 h blocks between 09:00 and 18:00 local, at most two per day, greedily by mean score (no τ).
A slot hits only if every hour clears ≤20 €/MWh; cancellation = 1 − hit rate.

| Ranker (all horizons) | Precision of top 70 h/month | Slot hit rate | Mean price announced | € /MWh above 20 on announced hours |
|---|---:|---:|---:|---:|
| Oracle (realised prices; upper bound) | 0.945 | 0.847 | 4.4 | 3.1 |
| Climatology | 0.753 | 0.633 | 20.9 | 15.2 |
| LightGBM classifier (raw = cross-fit ranking within month) | **0.792** | **0.658** | 19.6 | 14.7 |
| Ensemble P50 (lowest first) | 0.765 | 0.647 | 19.8 | **14.2** |

- The classifier beats climatology by only ~4 points of budget precision and ~2.5 points of slot
	hit rate. The oracle gap (0.79 → 0.95) is the real headroom.
- Ensemble P50 is the best slot ranker at D+1/D+2 (hit 0.715/0.695 vs classifier 0.664/0.665),
	the classifier from D+3 onward. Combining both is a cheap ML-C/ML-P experiment.
- **Filling the whole budget implies ~34% cancellations**, far above the ~10% target in
	project_plan §7. The agent needs a τ that leaves budget unused; tune it on blocked validation.
- Recorded for the refit rule: 132,048 train rows; P50 best iteration 150 (quantiles 61–424),
	classifier 299 (near-zero) / 487 (cheap). Cross-fit probability-order violations: 3,248 rows.

## Data and feature audit after the dev merge (2026-11-07)

**Merge repair.** Upstream `757105a` committed `calendar*.parquet` and `weather_fc.parquet`
through a text conversion (UTF-8 replacement bytes); none of the six files could be opened.
The valid calendars and the archived GFS `weather_fc` were restored, and the `build.py`
change that pointed the forecast join at observed-weather columns was reverted. The rebuilt
54-feature table matched the pre-merge table exactly; 135 tests passed; pushed as `e207d85`.
After every pull, check that each tracked Parquet opens before pushing.

**Weather: `weather_fc`, not `weather_hourly`.** `weather_hourly` (34 points, 10 variables
incl. humidity, precipitation, pressure, 10 m wind) is Open-Meteo *observed* archive weather.
At 10:00 on D nobody knows D+1…D+7's actual weather, so joining it to target hours would
leak the outcome; the extra variables do not change that. Valid uses are issue-relative lags
(e.g. trailing precipitation as a hydro proxy, after D−1 publication) and forecast-error
analysis. Extra variables as forecasts are now available through the same pipeline (next
section). Hydro storage (`entsoe_file_library/hydro_storage.parquet`) remains a more direct
hydro signal. `weather_hourly.parquet` stays in the repo for those lag/analysis uses.

**Calendar: `calendar.parquet` for Romania, HU/BG exports for neighbour features.**
`calendar_romania` held the same holiday/DST/day-hours values as `calendar.parquet` but
lacked 3,793 hours, the Oct 2025–Feb 2026 refit gap and the post-test horizon extension,
so it was removed. `calendar_moldova` was removed (Moldova is outside SDAC). `is_working_holiday`
is empty for Romania and `day_hours` duplicates the DST flag, so neither is a feature.
The HU/BG exports had the same refit gap, and the raw `holidays.csv` they were built from
lists only split-period dates (it missed e.g. Christmas 2025). The generator now covers the
continuous calendar range and adds the `holidays` package, the same source as the Romanian ML
calendar; on the old rows the regenerated holidays/bridge days are identical. HU/BG holidays
differ from Romanian ones on ~800 hours each, so they are the obvious next calendar feature.
The superseded manual `data/entsoe/` downloads (ignored) were moved to `~/GridSense_backups/`.

**Feature cleanup (default build now 50 features).**
- `f_solar_max_dm1`, `f_wind_mean_dm1`: 0% populated in train and validation (the source
	update mask keeps only recent generation), but ~97% in test. A tree never splits on an
	all-missing training column, and at refit they would switch on from late 2025 only. The
	builder now drops any feature with no training values and prints the list.
- `f_load_fc_min`, `f_load_fc_max`: now opt-in (`make features WEEK_AHEAD=1`). The data team's
	as-of build shows no train/validation forecast revision was recorded before issue time,
	and the ablation showed no meaningful gain.

Same-row validation, 54 → 50 features (`models.error_analysis`, default settings): ensemble MAE
by horizon changes by −0.02 to +0.16 €/MWh (largest at D+2: 19.88 → 20.04); ≤0 and 0–20 band
MAE worsen by 0.4–0.5; near-zero raw PR-AUC 0.7602 → 0.7639, cheap 0.6274 → 0.6195; budget
precision 0.792 → 0.783, slot hit rate 0.658 → 0.659. The week-ahead features carried a small,
unverified signal that may partly come from latest-revision leakage; restore them only with
as-issued vintages. Production artifacts were retrained on the 50-feature table: classifier
`20261107T162342-e207d85`, quantiles `20261107T162432-e207d85` (val MAE 22.595, coverage 80.0%).
Cross-fitted probability-order violations are now 5,558 rows (3,248 before), so the ML-C nesting
fix is more pressing. The [error analysis reports](../reports/real/eval/error_breakdown_val.csv)
now reflect the 50-feature default; the 54-feature tables quoted above are the earlier run.

## Real data status (current after latest pull)

The default training table now has **50 feature columns, all with training values**: 29
price/calendar, D−1 actual Romanian load, and 20 archived weather features. Week-ahead min/max
are opt-in (`WEEK_AHEAD=1`) and solar/wind D−1 lags are dropped automatically while the training
split has no values (see the audit above). Regional features are opt-in (`REGIONAL=1`). Capacity,
outage, hydro and flow tables are in the repo but not yet consumed by the feature builder.

| Data | Local status | Remaining work |
|---|---|---|
| RO hourly prices | 33,600 complete hours through 2026-10-31 from File Library | Final-test label gap resolved; refit and explicit authorization still required before evaluation |
| Actual RO load | Shared grid through Oct 2026; 33,220 available load hours; D−1 daily mean used | Check missing/re-stamped hours and historical publication latency. Forecast inputs still need as-of integration |
| Week-ahead RO load | File Library table: 1,436 delivery days, 2022-12-02→2026-11-15; as-of handoff has 0 train/val vintages | Opt-in only; needs original publication vintages before reuse |
| HU/BG prices + loads | File Library tables regenerated; 11 features integrated opt-in and ablated | Current-vs-regional gain small; validate price/load subsets and chronological blocks before promotion |
| HU/BG holidays | `calendar_hungary/bulgaria.parquet`, continuous through the refit gap | Candidate neighbour-holiday features |
| Actual generation by type | `entsoe_file_library/generation.parquet`; shared grid masks solar/wind by source update time | Resolve training-history availability; actuals remain issue-relative lags, not target-hour features |
| Installed capacity | `entsoe_file_library/installed_capacity.parquet` (annual, by type) and `unit_reference/` | Establish publication/as-of policy; scale solar/wind forecasts |
| Outages | `entsoe_file_library/outages.parquet` (normalized, versioned) | Data team: version/segment semantics and unit capacity unresolved; not model-ready |
| Weather | Archived GFS offsets for 4 RO points through validation end; observed `weather_hourly` for lags/analysis only | Extend archive for final refit/inference, verify original release timing, and obtain full D+7 operational runs |
| Reservoirs / physical flows | `entsoe_file_library/hydro_storage.parquet`, `physical_flows.parquet` | Release-aware lagged reservoir level/trend and D−1 RO↔HU/BG net flows |

The former manual `data/entsoe/` downloads (offered RO↔BG capacity, 2026 week-ahead, annual
capacity, year-ahead load) are superseded by the File Library tables and were moved to
`~/GridSense_backups/data_entsoe_manual_downloads/`.

Never use target-day `Actual min/max` columns. Native-time exports need their stated timezone:
cross-border capacity files say CET/CEST; File Library timestamps explicitly say UTC.

### What to collect or integrate next

| Priority | Checklist row / extra source | Action and training use |
|---|---|---|
| Collected; final evaluation still gated | 1: RO prices Aug–Oct 2026 [12.1.D] | Labels and issue-day price lags now complete; final refit and explicit test authorization still required |
| Integrated, improve provenance/coverage | Extra: archived **weather forecasts** | RO four-point GFS offsets added with conservative cutoff assumptions; next resolve exact run/release history, D+7, and HU/BG forecasts. No observed-target-weather substitution |
| Integrated opt-in, validate further | 4: HU/BG prices | Regional join/leakage tests and same-row ablation done; isolate feature subsets and confirm on chronological blocks |
| High | 3: actual generation [16.1.B&C] | Solar/wind first, hydro/nuclear next; D−1 same-hour/daily and 7-day summaries, never target actuals |
| High | 2: actual load + day-ahead forecast [6.1.A/B] | Actual load largely collected; extend it. Use target-day forecast only when original publication is before the issue cutoff; later day-ahead publications are unavailable at 10:00 |
| Done, provenance unresolved | 5: week-ahead load [6.1.C] | No more broad-history collection needed; keep min/max, fix vintage joins, then try expected-load deviation from the recent weekday profile |
| Medium / already downloaded | 6: capacity [14.1.A] | Integrate publication-safe capacity; strongest use is scaling solar/wind forecasts, not expecting a yearly scalar to explain hourly weather |
| Medium | 7: generation outages [15.1.A–D] | Nuclear/thermal/hydro unavailable MW for the target, latest version known at issue; never use final revised outage status retroactively |
| Medium–low | 8: reservoirs [16.1.D] | Last published weekly filling/energy level + trend, with release delay |
| Low | 9: physical flows [12.1.G] | Actual RO↔HU/BG net import lags D−1 and rolling means; current offered-capacity exports are a different item |

After weather/generation, try forecast residual demand (load minus forecast renewable output),
then public/licensed prior-day gas and carbon closes for price-level shifts. A 15-minute-market
flag alone has no variation in the current training period, so trees cannot learn its post-2025
effect without an explicit later development/refit design; it is not an immediate validation gain.

## ENTSO-E download checklist (one person per row)

| Who | Item (ENTSO-E code) | Menu |
|---|---|---|
| A | Day-ahead **prices** RO Aug–Oct 2026 [12.1.D]; HU, BG if not in snapshot | Market → Energy Prices |
| B | Actual total load + day-ahead forecast [6.1.A/B]; week-ahead forecast [6.1.C] 2023→2026 | Load |
| C | Actual generation per production type [16.1.B&C]; installed capacity [14.1.A]; reservoirs [16.1.D] | Generation |
| D | Unavailability of generation/production units [15.1.A–D]; cross-border flows [12.1.G] | Outages, Transmission |

Conventions: `data/raw/entsoe_csv/<item>/<zone>_<year>.csv`, CSV, UTC if offered, keep native resolution. Skip day-ahead wind/solar generation forecasts (published after our issue time). API token: register, then email transparency@entsoe.eu with subject "Restful API access".

## Next steps (ordered, revised 2026-11-07)

Done: real-data/week-ahead ablation, archived weather, Aug–Oct labels, regional join + leakage
tests + same-row ablation (kept opt-in). Every gain so far is 0.2–1.5% on a validation set that
also drives early stopping, CQR and the ensemble weight, so the order below puts the validation
design before further keep/drop decisions.

1. **Blocked validation first (ML-P, with ML-C).** Split validation into chronological blocks:
	early stopping, calibration/conformal/ensemble weight, and scoring on separate blocks (or
	rolling origin). Re-score the open decisions on it: regional price vs regional load subsets,
	week-ahead load, the weather grid, and a separate no-weather D+7 model.
2. **Rank by decision metrics, not overall MAE.** Use `models.error_analysis`: low-price-hour
	MAE, near-zero PR-AUC, precision at the 70 h/month budget, slot hit rate and €/MWh above
	threshold on announced hours. Revisit the ensemble weight after any feature change.
3. **Feature candidates (each through the same harness):** capacity-scaled solar/wind
	potential and residual-load proxy (needs a capacity publication/as-of rule); clear-sky index
	and solar elevation; HU/BG holiday flags (extend country calendars first); GFS run-to-run
	revision as an uncertainty feature; weather-aware LEAR (per-hour GHI/residual load only) and
	LightGBM `linear_tree`. Weather grid status is in the section below.
4. **Done (ML-C integration):** `p_cheap ≤ p_near_zero` is guaranteed by the nested conditional
	chain, including per-step cross-fitted calibration; the historical 9.1% violations predate
	that change. `make evaluate TASK=classify` is registered, and the weather helper now uses
	`predict_cross_fitted`. Remaining work is chronological model/slot validation and retraining
	old independent classifier artifacts, not clipping probabilities or registering the evaluator.
5. **Data team:** publication-verifiable archived weather with full D+7; week-ahead original
	publication times/revisions for an as-of join; why solar/wind actuals are masked across all
	of train (do not bypass the update-time mask); sourced per-region PV/wind capacity if the
	weather grid is to be capacity-weighted; weather archive extended through refit/inference.
6. **Agent owner:** export `missing_weather` as `degraded` while keeping the reason, write
	append-only run history atomically before notifying the watchdog, test on synthetic or
	validation replay first.
7. **Freeze, then final evaluation.** Freeze features, model settings, calibration and decision
	thresholds. For the refit through 2026-02-28 (which adds the low-price-rich 2025 months),
	scale boosting rounds with training size from the recorded best iterations rather than reusing
	a fixed count. Run the single test evaluation only when explicitly authorized.

## Gotchas

- macOS LightGBM needs `brew install libomp`.
- Calendar must extend 7 days past the last price date, or the newest issue date gets only D+1.
- Tests take ~45 s (LightGBM with 7 quantiles); run `make test` and `make lint` before committing.
- Schema changes (new tables for load forecast, neighbours, outages) belong to the data team: flag them, don't edit silently.
