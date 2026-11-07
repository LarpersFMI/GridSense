# ML plan

The ML side of GridSense: what we build, how two ML engineers split it, and how we work before the real data exists. Read with [project_plan.md](project_plan.md) §5–6 and the rules in the [README](../README.md).

## 1. What ML delivers

| Deliverable | Consumer | Where |
|---|---|---|
| `predictions.parquet`: `p_near_zero`, `p_cheap`, P10/P50/P90 per hour for D+1…D+7, with `top_features`, `model_name`, `model_version` | Agent team | `config.PROCESSED_DIR`, columns in `schemas.PREDICTIONS` |
| Evaluation: model vs baselines on the test set, by horizon and month | Slides, jury questions | `reports/real/eval/` |
| Calibration curve, threshold-ready probabilities | Agent decision rule | `reports/real/figures/` |
| SHAP explanations and similar past days per slot | Dashboard, chatbot | `top_features` column + `similar_days` helper |
| Error analysis (missed negatives, false alarms, by horizon) | One slide | `notebooks/` + `reports/real/figures/` |
| Drift signal (recent calibration and slot hit rate) | `model_drift` alert | small function in `models/metrics.py` |

All models are trained from scratch in this repo. No pretrained weights and no external model APIs. The brief would allow fine-tuning a pretrained model, but using one zero-shot wouldn't count.

## 2. Working before the data exists

The data layer is decoupled from ML through **files with a fixed contract**, not through code calls.

- **Contract:** `src/gridsense/schemas.py` lists the columns of every table. `gridsense.io.read(name)` / `write(df, name)` check them.
- **Fake mode:** `GRIDSENSE_DATA=fake` makes `config.PROCESSED_DIR` point to `data/fake/` and models/reports go under `models/fake/` and `reports/fake/` (all gitignored). Real mode uses `data/processed/`, `models/real/`, `reports/real/`. They never mix.
- **Fake generator** (`src/gridsense/synthetic/market.py`, `make fake-data`): writes `prices_hourly`, `grid_hourly`, `weather_fc` and `calendar` for 2023-01-01 → 2026-10-31 that follow the schemas and have plausible structure:
  - price = seasonal level + evening peak − solar effect + noise, where the solar effect grows each year and is stronger on weekends and holidays, so negatives cluster on spring/summer weekend middays and become more frequent over time;
  - weather forecasts = a "true" weather series + noise that grows with `lead_days`;
  - calendar from the `holidays` package (real), with DST days of 23/25 hours.
- **Switching to real data** means running `make data` (data team) instead of `make fake-data`. No ML code changes.
- **Never report a number obtained on fake data.** Fake mode exists only to make the pipeline run end to end.

The agent and demo teams are decoupled the same way: ML ships a fake `predictions.parquet` in the first hours, and they build against it.

## 3. ML architecture

```
features/build.py   tables from data layer  ->  training_table.parquet   (ML-A)
models/base.py      Forecaster interface: fit(train, val) / predict(table) -> OUTPUT_COLUMNS
models/baselines.py seasonal naive, climatology, solar rule, LEAR       (ML-A)
models/train.py     LightGBM classifier + quantile regressor            (ML-B)
models/calibrate.py isotonic calibration, conformal intervals           (ML-B)
models/predict.py   trained model -> predictions.parquet                (ML-B)
models/explain.py   SHAP top features, similar days                     (B: SHAP, A: similar days)
models/metrics.py   all metrics                                         (ML-A)
models/evaluate.py  runs every Forecaster through the same harness      (ML-A)
splits.py           assign_split(target_ts) -> train / val / test / None
```

Rules that keep two people from blocking each other:

1. **Training table contract** (`schemas.TRAINING_TABLE`): key columns `issue_ts`, `target_ts_utc`, `horizon_days`, labels `y_price`, `y_near_zero`, `y_cheap`. Every feature column starts with `f_`. Models use every `f_*` column automatically (`models.base.feature_columns`), so ML-A can add features without breaking ML-B's code.
2. **Every model implements `Forecaster`.** `evaluate.py` doesn't know which model it's scoring, so baselines and new models plug in without changes to the harness.
3. **Splits come only from `splits.assign_split`**, applied to `target_ts_utc`. Rows between validation and test (2025-10 → 2026-02) have no split label; they're only used in the final refit.
4. **Artifacts:** `models/<mode>/<model_name>/<version>/` with the model file and `metadata.json` (feature list, train range, params, git commit, validation metrics). `version` = short git SHA + timestamp.
5. **Experiment log:** each training run appends one row to `reports/<mode>/experiments.csv` (model, version, params, validation metrics). No MLflow; a CSV is enough for 24 hours.
6. **Test-set guard:** `make evaluate` scores validation by default. `make evaluate FINAL=1` scores the test set and writes `reports/real/TEST_EVALUATED`; the script refuses to run the test set again unless that marker is deleted on purpose.

## 4. Splitting ML between two people

Split by pipeline stage, with the training table and the `Forecaster` interface as the boundary.

| | **ML-A: features and evaluation** | **ML-B: models** (suggested for you, since you train on this machine) |
|---|---|---|
| Owns | `synthetic/market.py`, `features/`, `models/metrics.py`, `models/evaluate.py`, `models/baselines.py`, similar days, error analysis | `models/train.py`, `models/calibrate.py`, `models/predict.py`, SHAP, stretch models |
| Delivers | `training_table.parquet`, baseline scores, evaluation reports, plots | Trained models, `predictions.parquet` |
| Depends on | Data team's parquet files (fake until real) | ML-A's training table (fake until real) |

### Timeline

| Time | ML-A | ML-B |
|---|---|---|
| **H0–H1** | Agree on `TRAINING_TABLE` with ML-B. Write the fake generator. | Agree on `TRAINING_TABLE`. Write artifact layout and experiment log helpers. |
| **H1–H3** | Training table v0 on fake data: calendar, price lags as of issue time, weather by lead time. | Write a fake `predictions.parquet` (e.g. climatology + noise) and **hand it to the agent team**. |
| **H3–H6** | Metrics and evaluation harness. Three simple baselines through `Forecaster`. | LightGBM classifier end to end on the fake table: train → predict → `predictions.parquet` → evaluate. |
| **H4–H8** (real data lands) | Swap to real data. EDA: **count positives per split for both labels**, check gaps, DST days and the 15-minute switch. LEAR. | First real LightGBM classifier for `y_near_zero` and `y_cheap`. Recency weights. Compare with baselines on validation. |
| **H8–H12** | Features v2: regime features, neighbours (optional). Similar days (kNN). Error-analysis slices. | Quantile regressor. Isotonic calibration. Conformal intervals. Small Optuna search. Real `predictions.parquet` v1 to the agent team. |
| **H12–H16** | Sleep in shifts. | Sleep in shifts (start a longer tuning run first if useful). |
| **H16–H19** | Final test evaluation **together, once**. Error analysis. | Refit on all data up to 2026-02-28. SHAP `top_features`. Drift metric. Final `predictions.parquet`. |
| **H19–H22** | Results tables, figures for the slides. | Stretch model if everything above is done. Help with the demo. |

**Hand-offs:** training table v0 (fake) by H3; v1 (real) by about H6. Predictions v0 (fake) to the agent team by H3, v1 (real) by H12, final by H19.

## 5. Model options

| Model | What it gives | Effort | Verdict |
|---|---|---|---|
| Seasonal naive, climatology, solar rule | Required baselines | Low | **Core** (ML-A) |
| **LEAR** (Lasso autoregressive model, one Lasso per hour of day) | The standard day-ahead price benchmark; strong at D+1. Direct per-horizon variant for D+2…D+7. | Low–medium | **Core** baseline (ML-A) |
| Logistic regression (hour × month one-hot, splines on irradiance) | Well-calibrated linear benchmark for the classifier | Low | Optional |
| **LightGBM classifier** (`y_near_zero`, `y_cheap`) | Main probability model; handles non-linear weather × calendar interactions | Medium | **Core** (ML-B) |
| **LightGBM quantile regression** (P10/P50/P90) | Price range for the decision rule and expected-value calculation | Medium | **Core** (ML-B) |
| **Conformalized quantile regression** | Adjusts the P10–P90 range on validation so it really covers ~80%; strong answer for "how do you handle uncertainty?" | Low | **Strong** (ML-B) |
| **Analog / kNN similar days** | A model in its own right *and* the "similar cases from history" explanation the brief names | Low | **Strong** (ML-A) |
| Two-stage day-level model: P(day has ≥ k cheap hours) × hourly profile | More stable label (days instead of hours); maps directly to slot planning | Medium | Stretch |
| Day-type clustering (k-means on normalised 24-hour price curves) | Regime label ("solar-glut day", "evening scarcity") as a feature and a slide; the brief lists clustering among its ML problem types | Low–medium | Stretch |
| Small MLP or the Lago et al. day-ahead DNN (24 outputs per day), PyTorch, from scratch | Shows a neural model trained from scratch; rarely beats LightGBM on data this small | Medium | Stretch (ML-B) |
| Ensemble (weighted average of calibrated LightGBM, LEAR-derived probability, kNN), weights on validation | Usually a small, reliable gain | Low once the parts exist | Stretch |
| N-HiTS, TFT, DeepAR from scratch | Multi-horizon neural forecasters | High | **Skip**: setup cost, ~33k hourly points, and harder to keep leakage-safe in 24h |
| Pretrained foundation models (Chronos, TimesFM) | Zero-shot forecasting | — | **Skip**: we're training from scratch, and zero-shot use wouldn't count as our model |

Recommended order: baselines → LightGBM classifier → quantile regressor → calibration + conformal → LEAR → kNN similar days → one stretch item.

## 6. Targets and labels

- Issue time 10:00 Romanian time on day D; horizons D+1…D+7 (`config.HORIZONS_DAYS`).
- `y_price` = hourly mean of the 15-minute day-ahead prices.
- `y_near_zero` = `y_price ≤ 20` (primary). `y_cheap` = `y_price ≤ 0` (secondary).
- Before modelling on real data, ML-A posts the positive counts per split for both labels in the team chat. If `y_cheap` has very few positives in train, we report it only as a secondary result.

## 7. Features (ML-A)

All features are computed as of the issue time. The latest known prices are for day D.

| Group | Examples | Note |
|---|---|---|
| Calendar | hour, weekday, weekend, holiday, bridge day, month, day-of-year sin/cos, DST flag | From the target time |
| Horizon | `f_horizon_days` | One model for all horizons |
| Weather forecast | GHI and cloud cover at the solar points, 100 m wind at Constanța, temperature; national averages | Matching `lead_days` only |
| Price lags (relative to issue date) | same hour on D and D-6, min/mean of midday prices on D, rolling 7-day midday minimum | Never "the day before the target" for D+2 and later |
| Market state | negative hours in the last 7 and 30 days, rolling 30-day midday minimum | Captures the solar-growth regime |
| Grid lags | solar and wind actuals on D-1, load on D-1 | Actuals, so lagged only |
| Structural | installed solar capacity (yearly) | Optional |

A unit test should check leakage: for a sample row, recompute each lag feature from data strictly before the issue time.

## 8. Training (ML-B)

- **Data size:** ~33k hourly targets × 7 horizons ≈ 230k rows. LightGBM trains in seconds to minutes on this machine (Apple M5 Max, 18 cores, 48 GB).
- **Classifier:** objective `binary`, early stopping on validation average precision. Avoid heavy class re-weighting; if used, calibrate afterwards.
- **Recency weights:** `w = 0.5 ** (age_days / half_life)`, with half-life chosen on validation from {180, 365, ∞} days.
- **Quantile regressor:** one LightGBM per quantile (0.1, 0.5, 0.9); sort outputs per row so quantiles never cross.
- **Tuning:** Optuna with a small budget (about 50 trials) on validation; fix `config.RANDOM_SEED`.
- **Calibration:** isotonic regression on validation predictions. Preferred if time allows: rolling-origin out-of-fold predictions across validation months, so the calibrator sees predictions from models trained on similar amounts of data as the final refit.
- **Conformal:** on validation, compute how far actual prices fall outside P10/P90 and widen the interval by that amount (CQR) to reach 80% coverage.
- **Final model:** refit on everything up to 2026-02-28 with the chosen hyperparameters and number of boosting rounds, keep the calibrator and conformal adjustment from validation, then evaluate the test set once.
- **Neural stretch:** add `torch` only if we get there. Train on CPU for reproducibility (the model is small); MPS is available if it's too slow.

## 9. Evaluation (ML-A)

Every model goes through the same harness, on the same rows, by horizon:

- **Classification:** PR-AUC, precision@k (k = hours we would announce), Brier score, reliability curve.
- **Quantiles:** pinball loss per quantile, P10–P90 coverage.
- **Point price (for LEAR comparison):** MAE and RMSE on `y_price`.
- **Slot level** (with the agent's slot builder, or a simple 2–6 h block rule if it isn't ready): slot hit rate, cancellation rate.
- **Breakdowns:** by horizon, by month, weekend vs weekday, holiday.

Error analysis slide: missed negatives (holiday? cheap imports? weather miss?), false alarms (forecast sunny, actually cloudy), performance by horizon and month.

## 10. Explainability outputs

- `top_features` in `predictions.parquet`: top 3 SHAP contributions per row, e.g. `"ghi_craiova:+0.21; weekend:+0.12; neg_hours_7d:+0.08"`. The agent turns this into a sentence.
- `similar_days(issue_ts, target_date, k=3)`: nearest past days by weather and calendar features, with their actual prices. Used by the dashboard and the chatbot.

## 11. Definition of done

- [ ] `make fake-data features train predict evaluate` runs end to end in fake mode.
- [ ] The same commands run in real mode after `make data`.
- [ ] LightGBM beats at least the simple baselines on validation PR-AUC and Brier score, or we explain honestly why not.
- [ ] Reliability curve looks close to the diagonal after calibration.
- [ ] P10–P90 coverage is close to 80% on validation.
- [ ] Test set evaluated once; `reports/real/TEST_EVALUATED` exists; results and figures committed.
- [ ] `predictions.parquet` passes `io.check_columns` and the agent team has used it.
- [ ] Leakage test and split test pass.
