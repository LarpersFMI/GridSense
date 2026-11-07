# Price forecasting plan (ML-P)

Owner: ML-P. Goal: P10/P50/P90 of the hourly Romanian day-ahead price for every hour of D+1…D+7, issued at 10:00 on day D. Read with [ml_plan.md](ml_plan.md) (shared rules, interfaces, timeline) and the README rules.

## 1. What "done" looks like

- `PriceForecaster` (`src/gridsense/models/price.py`) beats the seasonal-naive baseline on every horizon and matches or beats LEAR overall, on validation.
- P10–P90 coverage is close to 80% on validation after conformal adjustment, at every horizon.
- `make train TASK=price` and `make predict` work in fake and real mode.
- Figures for the slides: error by horizon, coverage by horizon, a fan chart (P10–P90 band vs actual) for one spring week.
- The training table (`features/build.py`) is used by both ML people.

## 2. Fourier or autoregressive?

Both are useful, but as **parts** of the model, not as the whole model.

**Fourier terms: yes, as features.**
- Price seasonality has three cycles: daily (solar dip at noon, evening peak), weekly (weekends) and yearly (solar strength, heating).
- Sine/cosine terms of day of year (K = 2–3 harmonics) give a smooth yearly cycle. In linear models (LEAR, ARX) they work much better than 12 month dummies.
- The daily cycle is best handled by the hour of day (per-hour models in LEAR, an hour feature in LightGBM) and the weekly cycle by weekday/weekend/holiday flags. Those capture sharp effects that a few harmonics would smooth away.

**Fourier alone (Prophet, harmonic regression, extrapolating the series): no.**
- What drives the price is mostly external: solar and wind forecasts, temperature and demand, holidays, imports. A pure seasonal model can't see a cloudy Saturday coming.
- The seasonal *amplitude* keeps changing: each year more solar makes the midday dip deeper. A fixed harmonic pattern fitted on 2023 underestimates 2026.
- Prices have spikes (−50 to +1,000 €/MWh) and level shifts (2023 was still elevated after the 2022 energy crisis). Fourier fits average shape, not tails.

**Autoregressive: yes, strong for D+1, weaker further out.**
- Recent prices carry the current level and regime, which matters most at D+1 (LEAR is the standard benchmark there).
- The value of lags falls with horizon. By D+4…D+7 the weather forecast and calendar explain more than last week's prices.
- Keep forecasts **direct**: each horizon uses lags known at the issue time. Never feed D+1 predictions back in to forecast D+2.

**Recommended combination:** an ARX model (autoregressive + exogenous weather + calendar + Fourier yearly terms) as the strong linear benchmark, and LightGBM quantile regression with the same inputs as the main model.

## 3. Model ladder

Build in this order. Each step must run end to end before the next starts.

| # | Model | Details | Role |
|---|---|---|---|
| 0 | **Seasonal naive** | Price at the same hour 7 days before the target. Always known at issue time for horizons ≤ 7. Quantiles from its residuals on train, per horizon. | Required baseline; the denominator for relative MAE |
| 1 | **Profile (climatology)** | Mean price by month × weekday × hour on train. | Shows how much is pure seasonality |
| 2 | **LEAR / ARX** | One Lasso per (horizon group, hour of day). Inputs: price lags as of issue time, weather forecast for the target, calendar, Fourier yearly terms. Prices transformed with `asinh` (below). Quantiles from residuals per horizon. | Strong statistical benchmark |
| 3 | **LightGBM quantile** | `PriceForecaster`: one model per quantile, horizon as a feature, recency weights, early stopping on validation pinball loss. | Main model |
| 4 | **Conformal (CQR)** | Widen or narrow the P10–P90 range per horizon so validation coverage is 80%. | Honest uncertainty |
| 5 | Stretch: ensemble | Average LEAR and LightGBM quantiles with weights chosen on validation. | Usually a small, reliable gain |
| 6 | Stretch: small neural net | MLP with 24 hourly outputs per target day and a pinball loss, PyTorch, trained from scratch on CPU. | "Neural from scratch" slide |

Skip SARIMA/SARIMAX (slow and weak on hourly data with two seasonalities and exogenous inputs) and Prophet (pure Fourier, see above).

### Price transform

Prices can be negative and have huge spikes, which hurts linear models. Use the **inverse hyperbolic sine** transform, standard in electricity price forecasting:

$$\tilde y = \operatorname{asinh}\!\left(\frac{y - m}{s}\right), \qquad y = m + s \cdot \sinh(\tilde y)$$

with $m$ and $s$ the median and median absolute deviation of prices on the train split. It works with negatives, compresses spikes and is reversible. Because it's monotone, quantiles survive the round trip: the P10 of $\tilde y$ maps exactly to the P10 of $y$. So LightGBM can also be tried on the transformed scale; keep whichever gives the lower validation pinball loss.

### One model or several?

Try both on validation:
- one LightGBM per quantile with `f_horizon_days` as a feature (simplest, most data per model);
- separate models per horizon group: D+1, D+2–3, D+4–7 (lags matter more at D+1).

## 4. Training table (`features/build.py`)

You own this; the classification person adds features through the `f_` prefix.

**Row construction.** For each local issue date D, set `issue_ts` = D 10:00 Europe/Bucharest (in UTC). For each horizon h in 1…7, add one row per local hour of day D+h (23 or 25 rows on DST days). Labels: `y_price` = hourly mean price; `y_near_zero`, `y_cheap` from the thresholds in `config.py`.

**Features.** Everything is known at `issue_ts`.

| Group | Columns (all prefixed `f_`) | Known at issue because |
|---|---|---|
| Calendar | hour, weekday, is_weekend, is_holiday, is_bridge_day, month, is_dst, `doy_sin_k`, `doy_cos_k` for k = 1…3 | Calendar of the target |
| Horizon | horizon_days | — |
| Price lags | price at the same hour on D; price at the same hour 7 days before the target; D's min, mean, midday (11–15) min, evening (18–21) max | D's prices were published on D-1 afternoon |
| Price regime | rolling 7- and 30-day midday minimum; negative hours in the last 7 and 30 days; rolling 30-day mean | Computed over days ≤ D |
| Weather forecast (lead = h) | GHI, cloud cover, temperature at each point; 100 m wind at Constanța; national mean GHI of the solar points | Archived forecasts issued h days before the target |
| Grid lags | D-1 solar max, wind mean, load mean | D-1 actuals are complete by 10:00 on D |

**Leakage test (required):** for a random sample of rows, recompute each price and grid lag from the raw tables using only timestamps strictly before `issue_ts`, and assert they match.

### Feature backlog (after v0 works on real data)

Ordered by expected value for the effort. Each needs the data team to add a table (flag the schema change), then a few `f_` columns here.

| # | Data | Why it matters for Romanian prices | Known at issue for D+1…D+7? | Source |
|---|---|---|---|---|
| 1 | **Neighbouring day-ahead prices** (HU, BG; optionally DE as a solar-glut signal) | Romania is market-coupled with its neighbours; when interconnectors aren't congested, prices converge, and cheap Hungarian solar drives many Romanian negative hours. Use lags as of D: same-hour price on D, negative hours in the last 7 days, RO–HU spread. | Yes (lags) | ENTSO-E, same API |
| 2 | **Weather forecasts at neighbouring solar points** (e.g. Szeged/Budapest, Plovdiv) | Neighbours' midday solar oversupply flows into Romania. | Yes (forecast by lead) | Open-Meteo, same API |
| 3 | **Week-ahead load forecast** | Demand for the target days from the TSO. | Yes, D+1…D+7 | ENTSO-E (week-ahead total load forecast) |
| 4 | **Planned generation outages** (Cernavodă nuclear, large hydro/thermal units) | A Cernavodă outage removes ~700 MW of baseload; evening prices spiked to ~€1,000/MWh in one. Planned outages are announced weeks ahead. | Yes, if only outages published before the issue time are used | ENTSO-E unavailability of generation units (REMIT messages) |
| 5 | **Hydro conditions**: reservoir filling, Danube flow, precipitation | Hydro is a large share of Romanian generation; dry periods raise prices. Weekly signal. | Yes (lagged) | ENTSO-E reservoir filling where available; Open-Meteo precipitation |
| 6 | **Gas (TTF) and carbon (EU ETS) prices** | Gas plants set the evening price; this is the biggest driver of the price *level*. | Yes (yesterday's close) | Check licence first: we may only use public data. Ember publishes some carbon price data. |
| 7 | 15-minute market era flag (from 2025-10-01) | Market structure changed. | Yes | Calendar |

**Wars, political instability, news:** not as direct features. They act on Romanian prices *through* gas and carbon prices, import flows and outages, which rows 1, 4 and 6 already capture. There are only a handful of such events in the training window, too few for a model to learn from, and they move the price level over weeks rather than the hourly shape we forecast. Recency weights and the regime features absorb level shifts. Use them instead in error analysis ("these misses coincide with …") and as a talking point. A public geopolitical risk index exists (Caldara & Iacoviello GPR, daily) if you want to test it as a stretch feature, but don't expect much at a 1–7 day horizon.

**Pooling neighbours as extra training data (stretch):** train one model on RO + HU + BG rows with a country feature. Hungary has many more negative-price hours, so the model sees more extreme examples. Evaluate on Romanian rows only.

## 5. Fake market data (`synthetic/market.py`) — first task

Needed so you can train before the real data exists. It writes `prices_hourly`, `grid_hourly`, `weather_fc` and `calendar` in fake mode, following `schemas.py`, for 2023-01-01 → 2026-10-31.

- **True weather per location:** GHI = clear-sky shape (hour, day of year) × (1 − cloud), with daily cloudiness drawn per region; 100 m wind as an AR(1) process; temperature = yearly cycle + noise.
- **Weather forecasts:** true weather + noise whose standard deviation grows with `lead_days` (1…7), one row per (issue date, target hour, lead, location).
- **Grid:** solar output ∝ GHI × installed capacity that grows each year; wind ∝ wind³ (capped); load = base + temperature effect + weekday effect.
- **Price:** level (declining from 2023 to 2024, then flat) + evening peak + load effect − solar effect − wind effect + AR(1) noise + rare spikes. The solar effect grows with installed capacity, so negative hours appear on sunny spring/summer weekends and become more frequent each year.
- **Calendar:** real Romanian holidays from the `holidays` package; DST days with 23/25 hours.

The structure matters more than realism: price must depend on the weather *forecast* signal, so the pipeline and the leakage test are meaningful.

## 6. Training details

| Setting | Starting value | Tune on validation |
|---|---|---|
| Quantiles trained | 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95 internally; P10/P50/P90 exported | — |
| Learning rate / trees | 0.03, up to 2000 with early stopping (100 rounds) | yes |
| `num_leaves`, `min_child_samples` | 31, 50 | yes |
| Subsampling | rows 0.8, columns 0.8 | light |
| Recency half-life | 365 days | {180, 365, ∞} |
| Target scale | raw vs `asinh` | yes |
| Model layout | single vs per horizon group | yes |

- **Optuna:** about 50 trials, objective = mean pinball loss over P10/P50/P90 on validation (all horizons). Fix the seed.
- **Extra quantiles** (0.05…0.95) give an approximate price distribution. Interpolating it at 20 €/MWh gives P(price ≤ 20), a free baseline for the classification person.
- **Final model:** refit on all labelled data up to 2026-02-28 with the chosen settings and the best number of trees; keep the conformal adjustment from validation.
- **Speed:** ~230k rows; each LightGBM fit takes seconds to a minute on the M5 Max. A full Optuna run fits in well under an hour.

## 7. Evaluation

All on validation until the single final test run, broken down **by horizon**, and also by hour of day and month:

| Metric | Why |
|---|---|
| MAE and RMSE of P50 | Point accuracy |
| **rMAE** = MAE / MAE of seasonal naive | Standard in price forecasting; < 1 means better than naive |
| Pinball loss per quantile and mean | Quality of the whole range |
| P10–P90 coverage and average width | Honest uncertainty: coverage ≈ 0.8 with the narrowest width |
| MAE on hours with price ≤ 20 | Accuracy where the agent actually acts |
| Optional: Diebold–Mariano test vs LEAR | Shows the improvement isn't noise |

Figures: rMAE by horizon (all models), coverage by horizon (before/after conformal), fan chart for one spring week.

## 8. Conformal adjustment (CQR)

Per horizon, on validation: compute $E_i = \max(\hat q_{0.1,i} - y_i,\; y_i - \hat q_{0.9,i})$, take its 80th percentile (with the $\lceil (n+1) \cdot 0.8 \rceil / n$ finite-sample correction) as $\delta_h$, then use $[\hat q_{0.1} - \delta_h,\; \hat q_{0.9} + \delta_h]$. $\delta_h$ is negative when the raw interval is too wide. Store $\delta_h$ in the model's metadata.

## 9. Your timeline

| Time | Task | Output |
|---|---|---|
| H0–H1 | Agree on `TRAINING_TABLE` and the feature list with ML-C | Message in the team chat |
| H1–H3 | Fake market generator | `make fake-data` works |
| H3–H5 | `features/build.py` v0 (calendar, Fourier, price lags, weather by lead, regime) + leakage test | Fake `training_table`, shared with ML-C |
| H5–H6 | Seasonal naive and profile baselines; `GRIDSENSE_DATA=fake make train TASK=price` | Pipeline runs end to end |
| H4–H8 (real data lands) | Switch to real data; EDA (gaps, DST, 15-minute switch, price distribution per year); first real `PriceForecaster`; LEAR | First validation results table |
| H8–H12 | `asinh` vs raw, single vs per-horizon, recency half-life, Optuna; conformal | Tuned model, coverage plot |
| H12–H16 | Sleep in shifts (start Optuna before sleeping) | — |
| H16–H19 | Refit; final test evaluation together with ML-C, once | Test results |
| H19–H22 | Figures and slides; ensemble or neural stretch if time allows; then train the classifier too if ML-C needs it | Slides |
