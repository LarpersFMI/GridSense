# Zero-Cost Hours Agent: Hackathon Plan

**Hackathon:** 24h to Power PPC
**Challenge company:** PPC Energie, with links to PPC Blue and Rețele Electrice
**Deadline:** Sunday 12:00 (repository frozen). Live demo from 13:00: 5 minutes of demo plus 2 minutes of technical questions.
**Brief:** [Smarthack_XI_2026_Tema_PPC.pdf](Smarthack_XI_2026_Tema_PPC.pdf). Teams choose their PPC challenge after the opening presentation, so confirm this idea fits what PPC presents before committing to it.

---

## 1. One-line pitch

An AI agent that forecasts, days in advance, which hours will have negative or near-zero electricity prices in Romania. It then automatically plans, confirms and announces "zero-cost hours" to the right PPC Energie customers, so PPC moves consumption into cheap solar hours without ever giving away energy during expensive ones.

## 2. Why this matters to PPC

- **The market problem is real and growing.** Romania had 187 negative-price hours across 45 days in 2025. In spring 2026 some days had 7 consecutive negative hours, down to about –50 €/MWh. In the evenings, prices reached as high as €1,000/MWh while a Cernavodă unit was offline. ANRE says congestion and negative prices at solar peak are already happening.
- **PPC Energie is already testing the idea.** The 2026 "Energie Electrică Activă Zero" pilot gave 5,000 customers zero-cost intervals, announced at least 12 hours ahead by email and myPPC. Over 83% of the enrolled households shifted consumption, about 71 MWh in total, and about 78% opened the notifications. The pilot offered roughly 70 free hours per customer per month.
- **What our agent adds.** The pilot shows customers respond. Our agent turns that manual, short-notice pilot into an automated product: a multi-day outlook with confidence levels, automatic confirmation or cancellation after the day-ahead auction, smart choice of which customers to invite, and a cost-controlled budget.
- **Cross-company bonus.** Zero-cost hours are ideal EV charging windows (PPC Blue), and shifting load toward solar hours relieves the evening peak and congestion on the grid (Rețele Electrice).

## 3. How it maps to the slide's four steps

| Step | What our agent does |
|---|---|
| **Perceive** | Pulls Romanian day-ahead prices, load and generation (ENTSO-E), weather forecasts (Open-Meteo), and the holiday calendar. |
| **Estimate** | Our own model predicts, for each hour over the next 1–7 days, the probability of a negative or near-zero price, plus a price range (P10/P50/P90). |
| **Decide** | Picks zero-cost slots using thresholds tuned on validation data, a monthly free-hours budget, and the confidence of each forecast. Sends low-confidence or bad-data cases to a human. After the auction it confirms or cancels each slot. |
| **Act** | Publishes the weekly calendar, sends customer notifications, recommends EV charging windows, alerts the trading desk, escalates uncertain cases for human review, and writes a weekly report. |

## 4. Mandatory requirements checklist

- [ ] **Our own ML model.** A LightGBM classifier and quantile regressor trained in our repo, running locally, not through an external API.
- [ ] **Separate test set.** A time-based split; the test period is never touched during tuning.
- [ ] **Simple baseline.** Same hour last week, a seasonal frequency table, and a solar-threshold rule.
- [ ] **Training code in the repository.**
- [ ] **LLM used only for orchestration and wording.** All decisions come from our model plus the decision rules.
- [ ] **Actions, not just chat.** Calendar, notifications, alerts and reports.
- [ ] **Public or synthetic data only, with sources cited in the README.**
- [ ] **Public GitHub repo with commits spread across the 24 hours.** Commit small and often; the commit history is scored.
- [ ] **The agent can say "I'm not sure" and hand the case to a human** (`NEEDS_REVIEW` label plus an escalation action).
- [ ] **Presentation materials (slides, notebooks) committed to the repo.**

## 5. Data

### 5.1 Sources

| Data | Source | Notes |
|---|---|---|
| Day-ahead prices for Romania | ENTSO-E Transparency Platform (bidding zone `10YRO-TEL------P`) | Use the `entsoe-py` library. Since the move to 15-minute market periods in late 2025, aggregate to hourly (keep the hourly minimum too). Requires a free API token, so request it **immediately**. Fallback: manual CSV export from the ENTSO-E site or OPCOM's published PZU results. |
| Actual load and generation by type | ENTSO-E | Used only as **lagged** features (values known at issue time). ENTSO-E day-ahead wind/solar forecasts are published the evening before delivery, so they are **not** available at 10:00 on D for D+1 or later. Don't use them as features. |
| Weather | Open-Meteo **Previous Runs API** (`previous_day1` … `previous_day7`) | Gives the forecast as it was issued N days before the target, so D+5 features carry real D+5 forecast error. The Historical Forecast API stitches the first hours of each run (≈ same-day forecast) and would make long horizons look too good. Check how far back Previous Runs goes for the chosen weather model; if it doesn't cover the whole training window, add noise that grows with horizon to the older data and document it. Points: Bucharest, Constanța (Dobrogea wind), Craiova and Timișoara (solar regions). Variables: shortwave radiation, cloud cover, 100 m wind speed, temperature. |
| Public holidays | Python `holidays` package (Romania) | Holidays and weekends strongly raise the chance of negative prices. |
| Neighbouring markets (optional) | ENTSO-E prices for Hungary and Bulgaria | Cheap power flowing in from the west drives some Romanian negative hours. |
| Customer response (stretch goal) | Low Carbon London smart-meter dataset, which includes a dynamic time-of-use trial with day-ahead price signals | Lets us estimate how much load households actually shift. Verify the licence and format before relying on it. |
| Customer portfolio | **Synthetic**, calibrated to the pilot figures above | Segments: EV owners, heat-pump households, prosumers, standard households. Clearly labelled as synthetic in the README. |

### 5.2 Time split

- **Train:** 2023-01-01 → 2025-02-28
- **Validation (tuning, calibration, decision thresholds):** 2025-03-01 → 2025-09-30
- **Refit:** on everything up to 2026-02-28, with the hyperparameters and thresholds chosen on validation.
- **Test (touched once, for the final report):** 2026-03-01 → 2026-10-31

The validation window must include spring and summer. A winter window (Oct–Feb) has almost no negative hours, so calibration and the threshold sweep would be meaningless there. Spring 2026 contains the record solar and negative-price days, so the test set is a hard, realistic challenge. Use sample weights that favour recent data, because installed solar keeps growing. If time allows, add rolling-origin CV by month inside train + validation.

Split dates live in `src/gridsense/config.py`; never hard-code them elsewhere.

## 6. The ML model

### 6.1 Targets

For every target hour *h*, forecast issued at 10:00 (Romanian time) on day D for target days D+1 … D+7. D+1 is forecast before the day-ahead auction closes (13:00 Romanian time), so it is still a real forecast.

1. `is_near_zero`: hourly mean price ≤ 20 €/MWh. **Primary label.** It has enough positives in the training window to learn from.
2. `is_cheap`: hourly mean price ≤ 0 €/MWh. Reported as a secondary result; count its positives in train before relying on it.
3. Price quantiles P10, P50 and P90, from a LightGBM quantile regression (sort the outputs so the quantiles never cross).

Labels use the **hourly mean** of the 15-minute prices. The hourly minimum is kept as a feature and for analysis only.

### 6.2 Features (only information available at the time of the forecast)

One training row per **(issue_date, target_hour, horizon)**. Every feature is computed **as of 10:00 on the issue date**. At that moment the latest known prices are for day D (published the afternoon of D-1).

- **Calendar:** hour, weekday, weekend flag, holiday flag, day before or after a holiday, month, day of year (sine and cosine), DST flag.
- **Weather forecast for the target hour** (with the matching lead time): irradiance and cloud cover at the solar points, wind at Dobrogea, temperature.
- **Recent market state (relative to the issue date, not the target):** price at the same hour on day D and on D-6, rolling 7-day minimum midday price, count of negative hours in the last 7 days.
- **Regime features:** negative-hour count over the last 30 days, rolling 30-day minimum midday price, installed solar capacity (ENTSO-E, yearly). Tree models can't extrapolate the solar growth trend, so these give them the current level.
- **Horizon in days**, so a single model learns that confidence drops further ahead.

### 6.2.1 D+1 and autoregressive models

For D+1, recent prices carry most of the signal, so autoregressive models work well there:

- **LEAR** (Lasso-estimated autoregressive model: one Lasso regression per hour of the day, on the last few days' 24-hour price vectors plus calendar and weather inputs) is the standard benchmark for day-ahead price forecasting. Train it from scratch with scikit-learn as a strong D+1 baseline.
- For D+2…D+7, use **direct** forecasting (a separate target per horizon, lags taken as of the issue date), not recursive forecasting. Feeding D+1 predictions back in as inputs compounds the error.
- The LightGBM model already behaves autoregressively through its lag features. LEAR is the comparison that shows it adds value over a well-tuned linear AR model.

### 6.3 Baselines (all reported on the same test set)

1. **Same hour last week** (seasonal naive, last week as known at issue time).
2. **Climatology:** historical frequency of negative prices by month × weekday × hour, fitted on train only.
3. **Rule:** forecast irradiance above a threshold and weekend → cheap.
4. **LEAR** (D+1, and direct variants for longer horizons if time allows): the strong statistical baseline.

### 6.4 Metrics

- **PR-AUC and precision@k** (the hours we would actually announce). Plain accuracy is misleading at ~3% positives.
- **Brier score and a calibration plot.** The agent relies on these probabilities, so they must be honest. Apply isotonic calibration on validation.
- **Pinball loss and interval coverage** for the price quantiles (does the P10–P90 range contain about 80% of actual prices?).
- **Slot-level metrics** (what PPC actually experiences): slot hit rate (share of announced slots where every hour cleared at or below the threshold) and cancellation rate.
- All metrics broken down **by horizon** (D+1 vs D+7).

### 6.5 Error analysis (one slide)

- Negative hours we missed: were they holidays, cheap imports from the west, or a weather forecast miss?
- False alarms: cloudy days the forecast said would be sunny.
- Performance by month and by horizon.

## 7. The agent

### 7.1 Daily loop

1. **10:00 – Outlook.** Run the model for D+1 … D+7. Build candidate slots: contiguous 2–6 hour blocks between 09:00 and 18:00.
2. **Score each slot.** Combine the slot's average probability of being cheap, its expected price (P50) and its worst case (P90).
3. **Plan within constraints.** Respect the monthly free-hours budget per customer (pilot level: about 70 hours), a cap on PPC's expected cost, and a maximum number of slots per day.
4. **Publish a provisional calendar** with a confidence label per slot: *Confirmed*, *Likely*, *Possible*.
5. **~14:00 Romanian time – After the day-ahead auction results for D+1.** Compare actual prices with the plan. Confirm slots where the price is at or below the threshold, cancel slots that cleared expensive, and optionally add surprise cheap slots. Notifications go out at least 12 hours ahead, matching the pilot.
6. **Act.** Send segment-targeted notifications, EV charging recommendations, a trading-desk alert summarizing expected shifted volume, and an evening scarcity alert when the P50 evening price exceeds a high threshold.
7. **Weekly report.** Energy shifted, value to PPC, customer savings, cancellations, and forecast accuracy.

### 7.2 Decision rule (simple, tunable, explainable)

For a candidate slot *s*:

```
expected_value(s) = shifted_kWh(s) × (evening_price_P50 − slot_price_P50)
                    − cancel_penalty × P(not cheap | s)
announce s as "Likely" if  P(cheap | s) ≥ τ_likely  and  expected_value(s) > 0  and budget allows
announce s as "Possible" if τ_possible ≤ P(cheap | s) < τ_likely
```

- `shifted_kWh(s)` comes from the segment response assumptions, calibrated to the pilot: about 71 MWh over 6 intervals for 5,000 customers, roughly 2.4 kWh per customer per interval. EV owners are assumed to shift more.
- **Thresholds τ are chosen for a reason.** Sweep τ on the validation set and plot net value against the cancellation rate. Pick the point that keeps cancellations below about 10%, because cancelled promises damage customer trust. Show this curve in the demo.
- **Low confidence leads to a conservative decision.** When weather data is missing or the horizon is long, the probabilities widen, and the agent announces fewer slots or labels them only as "Possible."
- **"I'm not sure" goes to a human.** A slot is labelled `NEEDS_REVIEW` and sent to an operator instead of being announced when the input data fails validation, the P10–P90 range is very wide, or the probability is close to the threshold for a high-value slot. The brief asks for this explicitly.

### 7.3 Customer targeting

| Segment | Message | Why |
|---|---|---|
| EV owners | "Charge between 11:00 and 15:00 on Saturday" with a link to the nearest PPC Blue charger | Largest flexible load |
| Heat-pump / AC households | Pre-heat or pre-cool suggestions | Flexible thermal load |
| Prosumers | "Store or use your own solar now; export prices will be negative" | Fits the MaxControl offer |
| Standard households | Laundry and dishwasher timing | Broad reach |

### 7.4 Where the LLM is used (and where it is not)

- **Used for:** turning the plan and SHAP explanations into friendly notification text in Romanian and English, writing the weekly report, and an optional chat interface ("Why is Saturday marked Likely?").
- **Not used for:** any prediction or decision. Those come only from our model and the decision rule.

## 8. Robustness (10 points)

- **Missing weather or price data.** Fall back to climatology with wider uncertainty; the agent automatically becomes more conservative. Show this live in the demo.
- **Wrong input data** (listed separately in the brief). Validate inputs before the model runs: missing or duplicate timestamps, prices outside a plausible range (e.g. below –500 or above 4,000 €/MWh), irradiance at night, and stale forecasts. Failed checks set `data_quality` on the prediction, and the decision rule routes those slots to `NEEDS_REVIEW`.
- **Holidays and unusual days.** Explicit features and a dedicated error-analysis slice.
- **DST changes.** Handle 23- and 25-hour days. Romania's clocks went back on 25 October 2026, so this is fresh.
- **15-minute market periods.** Aggregate consistently and keep hourly minimums.
- **Data drift.** Weight recent data and monitor calibration weekly; the report flags when accuracy drops.
- **Unit tests** for the decision rule: never exceed the budget, never confirm a slot whose cleared price is above the threshold.

## 9. Explainability (10 points)

- **SHAP values for every slot**, turned into one sentence, for example: "Saturday 11:00–15:00 is *Likely* (P = 0.81) mainly because irradiance is forecast to be high, it's a weekend, and there were 4 negative hours last weekend."
- **Decision trace.** A log for each slot showing probability, thresholds, budget and the final decision.
- **Threshold curve** explaining why τ was set where it is.
- **Similar days from history** (the brief names this as an example): for each slot, show the 3 nearest past days by weather and calendar features and what the price actually was on them.

## 10. Repository structure

See the README for the current layout. In short: `src/gridsense/{data,features,models,agent,llm,synthetic}`, a Streamlit demo in `app/`, tests in `tests/`, and gitignored `data/` and `models/` folders that the scripts recreate. Shared paths, split dates and thresholds are in `src/gridsense/config.py`; the parquet column contract between teams is in `src/gridsense/schemas.py`.

## 11. 24-hour timeline

H0 = when hacking starts (assumed Saturday about 12:00). Adjust to the real start time.

The team is split into **data engineers** and **ML engineers**. The agent (C) and the demo (D) together are worth 30 points, so give each a named owner from the start, even if that person also does data or ML work.

- **A – Data engineers:** downloads, cleaning, 15-min → hourly, calendar, input validation. They deliver the parquet files in `schemas.py`.
- **B – ML engineers:** training table, baselines (including LEAR), LightGBM classifier + quantile regressor, calibration, evaluation, SHAP, error analysis. They deliver `predictions.parquet`.
- **C – Agent & decision engine owner**
- **D – Demo app, pitch & integration owner**

| Time | A | B | C | D |
|---|---|---|---|---|
| **H0–H1** (all) | Agree on scope, targets and split; create the repo; **request the ENTSO-E token now** | | | |
| **H1–H4** | Download prices, load, generation, weather; clean; 15-min → hourly | Pull a quick price CSV yourself so you aren't blocked; build baselines; set up the evaluation framework | Synthetic customer portfolio; decision rule skeleton with dummy probabilities | Streamlit skeleton: calendar view, slot cards, map/segment view |
| **H4–H8** | Feature pipeline (as-of-time safe), holidays, DST | First LightGBM classifier; compare with baselines on validation | Planner: candidate slots, budget, confirm/cancel logic | Wire app to agent outputs; draft pitch storyline |
| **H8–H12** | Neighbouring-market features; data quality checks | Quantile regressor; LEAR for D+1; calibration; tune on validation | Actions: notifications (LLM wording), EV recommendations, alerts, human escalation, report | Replay mode for a real week |
| **H12–H16** | Sleep in shifts (two people at a time) | | | |
| **H16–H19** | Robustness tests: missing data, holidays | **Final test-set evaluation (once)**; error analysis; SHAP | Threshold sweep on validation; decision trace; unit tests | Integrate SHAP explanations and threshold curve into the app |
| **H19–H22** | README: data sources, setup, reproduce | Results tables and plots for the slides | End-to-end run from fresh clone | Slides; rehearse the 5-minute demo twice |
| **H22–H24** | **Freeze features.** Fix bugs, clean repo, final push before **Sunday 12:00** | | | |
| **12:00–13:00** | Rehearse; prepare answers for the technical questions | | | |

**Rule:** if the ENTSO-E token has not arrived by H3, switch to the manual CSV export and keep going.

## 12. Five-minute demo script

1. **0:00–0:45 – The problem.** A chart of Romanian prices on one spring day: deeply negative at noon, very high in the evening. "PPC Energie's pilot showed 83% of customers will shift. But it's manual and gives only 12 hours' notice."
2. **0:45–1:30 – Our model.** A single slide: model vs. three baselines on the 2026 test set, plus the calibration plot.
3. **1:30–3:30 – Live replay of a real week from the test set** (choose an April or May 2026 week with negative hours):
   - The agent's provisional calendar at D-5, with confidence labels.
   - The auction result arrives: one slot is confirmed, one is cancelled, and the cancellation is explained.
   - Notifications per segment, including the EV charging recommendation.
   - Click a slot and see "Why?" with the SHAP explanation.
4. **3:30–4:15 – Robustness.** Remove the weather feed live: the agent widens uncertainty and announces fewer slots.
5. **4:15–5:00 – Impact.** The weekly report: MWh shifted, value to PPC, customer savings, cancellation rate. Close with the scaling story from 5,000 to 3 million customers, plus PPC Blue and grid benefits.

## 13. Prepare for these technical questions

- **"Day-ahead prices are known the day before. Why forecast?"** The D+1 forecast is issued before the auction closes, so the trading desk can use it when bidding. The main value is the 2–7 day outlook: customers plan days ahead, and the auction result is used only to confirm or cancel.
- **"How did you avoid data leakage?"** Features are built "as of" the forecast time, weather features are archived forecasts with the matching lead time, and the test period was used only once.
- **"Why these thresholds?"** Show the validation sweep and the trade-off between value and cancellations.
- **"How well is it calibrated?"** Show the calibration plot and the Brier score against the baselines.
- **"What's synthetic?"** Only the customer portfolio and response assumptions, calibrated to the published pilot figures. All market and weather data is real and public.
- **"What would you need from PPC to deploy this?"** Real smart-meter data for response modelling, retail margins, and integration with myPPC notifications.

## 14. Risks and fallbacks

| Risk | Fallback |
|---|---|
| ENTSO-E token delayed | Manual CSV export from ENTSO-E or OPCOM |
| Historical forecast weather missing for early dates | Start training in 2022 or later, or use reanalysis data with added noise and state it clearly |
| Too few negative hours to learn from | Already handled: `is_near_zero` is the main label and `is_cheap` is a secondary result |
| Model barely beats the baselines | Still a valid result if shown honestly; focus on calibration and agent value |
| LLM API unavailable during demo | Template-based notification text as backup |
| Time runs out | Drop the stretch goals (customer-response model, neighbouring markets) first; never drop the test-set evaluation |

## 15. Scoring self-check

| Criterion | Points | Our evidence |
|---|---|---|
| Idea & relevance for PPC | 25 | Extends PPC Energie's real 2026 pilot; ties into PPC Blue and Rețele Electrice |
| ML quality | 25 | Real public data, time-based split, three baselines, calibration, error analysis |
| The agent | 25 | Full loop from forecast to plan, confirmation, targeting, notifications and report |
| Robustness | 10 | Missing-data fallback, holidays, DST, 15-min periods, unit tests |
| Explainability | 10 | SHAP per slot, decision trace, threshold curve |
| Demo & repository | 5 | Replay demo, reproducible README, clean structure |

## 16. Sources

- PPC €24 billion plan to 2030, 21% for Romania: https://balkangreenenergynews.com/ppc-to-invest-eur-24-billion-with-focus-on-balkan-expansion/
- PPC €3 billion for Romania 2026–2028, ~€800 million for distribution: https://www.forbes.ro/?p=475563
- PPC Renewables Romania target of 2 GW by end-2026: https://businessforum.ro/energy/20260123/ppc-romania-aims-to-reach-2-gw-in-green-capacities-in-2026-2779
- PPC battery storage at Romanian wind farms: https://balkangreenenergynews.com/?p=89819
- Romania 2025 grid review (187 negative-price hours): https://www.electricitymaps.com/grid-in-review-2025/romania
- 7 negative hours down to –50 €/MWh (OPCOM): https://economedia.ro/?p=334899
- Evening prices up to €1,000/MWh during Cernavodă outage: https://www.romania-insider.com/cernavoda-reactor-restart-energy-price-july-2026
- ANRE on congestion and negative prices: https://financialintelligence.ro/interviu-george-niculescu-anre-reteaua-e-provocarea-structurala-car&
- PPC Energie zero-cost pilot results: https://www.economica.net/?p=952038
- PPC Energie pilot design (~70 free hours per month): https://www.forbes.ro/?p=500324
- PPC MaxControl prosumer offer: https://stiricraiova.ro/2026/07/15/ppc-energie-lanseaza-ppc-maxcontrol-oferta-pentru-prosumatori-cu-plata-soldului-la-30-de-zile-si-protectie-impotriva-preturilor-negative/
- Romanian prosumer numbers: https://www.capital.ro/prosumatorii-devin-al-doilea-producator-de-energie-din-romania-investitii-de-peste-22-miliarde-de-euro.html
- Rețele Electrice 2025 investments, smart meters, AADMS: https://economedia.ro/retele-electrice-romania-parte-din-grupul-ppc-in-romania-a-investit-aproximativ-14-miliarde-de-lei-in-proiecte-anul-trecut.html
- PPC Blue network size: https://informat.ro/en/current-affairs/ppc-blue-launches-the-campaign-charge-and-win-for-electric-vehicles-133526
- ENTSO-E Transparency Platform: https://transparency.entsoe.eu
- Open-Meteo (Historical Forecast API): https://open-meteo.com