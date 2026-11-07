# ML handoff (price forecasting, ML-P)

State as of 2026-11-07, branch `dev` (last pushed commit `0a3673d add LEAR`). Read this first, then [price_plan.md](price_plan.md), [ml_plan.md](ml_plan.md) and the README rules.

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

## Real data status (manual ENTSO-E downloads, no API token yet)

In `data/entsoe/` (**untracked, not gitignored**; move to `data/raw/entsoe_csv/` or decide to commit deliberately):

| Folder | Actually contains | Usable? |
|---|---|---|
| `day_ahead/` (2026-01→2026-11-08, monthly) | **Offered cross-border capacity RO↔BG**, not prices | Only as a low-priority capacity feature; prices still needed |
| `week_ahead/` (2026 weeks 1–16) | Week-ahead load forecast: daily min/max per day, plus actual min/max | Yes, forecast columns only; needs 2023-01→2026-10 |
| `year_ahead/` (2020–2026) | Year-ahead load forecast: weekly min/max, plus actuals | Low value; forecast columns only |

Leakage rules for these files:
- `Actual min/max` columns are **not known at issue time** for the target; only use them as lags (days ≤ D-1).
- Week-ahead forecasts are published once a week for the following week (verify the publication day). Use a forecast for target day T only if it was published on or before the issue date; otherwise NaN.
- Timestamps are CET/CEST, not UTC or Bucharest time.

Still needed (checklist below): RO prices Aug–Oct 2026 (snapshot covers ≤ 2026-07-31), actual load + generation per type (RO, 2023→2026), HU/BG prices (check snapshot first), installed capacity, outages (with publication time), reservoirs.

## ENTSO-E download checklist (one person per row)

| Who | Item (ENTSO-E code) | Menu |
|---|---|---|
| A | Day-ahead **prices** RO Aug–Oct 2026 [12.1.D]; HU, BG if not in snapshot | Market → Energy Prices |
| B | Actual total load + day-ahead forecast [6.1.A/B]; week-ahead forecast [6.1.C] 2023→2026 | Load |
| C | Actual generation per production type [16.1.B&C]; installed capacity [14.1.A]; reservoirs [16.1.D] | Generation |
| D | Unavailability of generation/production units [15.1.A–D]; cross-border flows [12.1.G] | Outages, Transmission |

Conventions: `data/raw/entsoe_csv/<item>/<zone>_<year>.csv`, CSV, UTC if offered, keep native resolution. Skip day-ahead wind/solar generation forecasts (published after our issue time). API token: register, then email transparency@entsoe.eu with subject "Restful API access".

## Next steps for me

1. ~~Real-data run~~ done with prices + calendar (above). Rerun `make features train TASK=price evaluate` when grid/weather tables land.
2. Neighbour price lags (HU/BG) as `f_` features + leakage test.
3. Week-ahead load forecast feature: data is in `data/raw/entsoe_file_library/TotalLoadForecast_6.1.C_D_E_r3/` (2023–2025, RO only). `UpdateTime(UTC)` was re-stamped at the 2025 platform migration, so use the publication rule (forecast for week W known after week W-1 ends), not the timestamp.
4. Optuna on LightGBM (~50 trials); weather forecasts are the bigger expected gain once available.
5. ~~LEAR + LightGBM ensemble~~ done; revisit the weight after new features.
6. Final refit, single test evaluation with ML-C, figures (rMAE and coverage by horizon, fan chart).

## Gotchas

- macOS LightGBM needs `brew install libomp`.
- Calendar must extend 7 days past the last price date, or the newest issue date gets only D+1.
- Tests take ~45 s (LightGBM with 7 quantiles); run `make test` and `make lint` before committing.
- Schema changes (new tables for load forecast, neighbours, outages) belong to the data team: flag them, don't edit silently.
