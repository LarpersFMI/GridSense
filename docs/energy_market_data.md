# Romanian day-ahead prices

The market pipeline lives in `gridsense.data`. It uses the repository's date and path
configuration, the `PRICES_HOURLY` schema and `gridsense.io.write`. The weather workstream's
contract is `weather_fc.parquet`, with one archived forecast per issue date, target UTC
hour, lead day and location. At implementation time its ingestion function was a stub.

## Reproduce

From the repository root with [uv](https://docs.astral.sh/uv/) installed:

```bash
uv sync --locked

# Small real sample. A Romanian spring DST day has 23 delivery hours.
uv run python -m gridsense.data.build --source snapshot --start 2025-03-30 --end 2025-03-30

# Rebuild the longer token-free dataset after trying the sample.
uv run python -m gridsense.data.build --source snapshot --start 2023-01-01 --end 2026-07-31 --allow-gaps

# Direct API. Set ENTSOE_API_TOKEN in the environment or ignored .env first.
uv run python -m gridsense.data.build --source entsoe --start 2025-09-30 --end 2025-10-02
make data
```

Both dates are inclusive Romanian calendar dates. `make data` uses the direct API, from
the configured train start to the end of the test period. It builds price data only.
Each successful run replaces the price outputs for the requested range. Failed coverage
checks leave previous outputs in place. Run in `GRIDSENSE_DATA=real` (the default).

- **Direct source.** [ENTSO-E Transparency Platform A44](https://transparencyplatform.zendesk.com/hc/en-us/articles/17703493179028-Guidance-on-Creating-a-Support-Ticket),
  daily contract A01, Romanian bidding zone `10YRO-TEL------P`. The pipeline uses UTC
  requests of up to one month, preserves the XML responses, and requires the
  [API token](https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188-How-to-get-security-token)
  for uncached requests. This route was tested with XML fixtures; a live authenticated
  run requires a token.
- **Token-free source.** The [pinned hsilvosa snapshot](https://huggingface.co/datasets/hsilvosa/entsoe-day-ahead/tree/d96677b452e97ebbeec83f9c00939a46e9c21c43)
  is a third-party Parquet export of ENTSO-E A44. GridSense downloads only the two original
  shards covering Romania (about 40 MB in total), checks their SHA-256 digests, and filters
  by EIC and date. Selected rows must use EUR/MWh and the daily contract. This snapshot
  ends at 2026-08-01 00:00 UTC.
  It contains gaps and lacks original period boundaries and publication timestamps. Use
  the direct API for newer data or to investigate gaps. Review the applicable source terms
  before redistributing data.
- **OPCOM.** The [operator's DAM report](https://www.opcom.ro/grafice-ip-raportPIP-si-volumTranzactionat/en)
  publishes Romanian market results in EUR/MWh. Its advertised historical CSV endpoint
  returned HTTP 403 during verification, so it is not an ingestion backend here.

## Outputs and checks

| Location | Contents |
| --- | --- |
| `data/raw/entsoe_prices/api/` | Unchanged ENTSO-E XML responses, named by UTC query window. |
| `data/raw/entsoe_prices/snapshot/<revision>/` | Unchanged, pinned Parquet shards. |
| `data/processed/prices_native.parquet` | One row per validated source interval. |
| `data/processed/prices_hourly.parquet` | Shared ML table with one row per complete hour. |
| `data/processed/prices_quality.json` | Requested and observed UTC bounds, counts by resolution, negative observations, coverage, and gap examples. |

The native columns are `ts_utc` and `interval_end_utc` (UTC timestamps, nanosecond dtype),
`price_eur_mwh` (float64), `resolution` (`PT60M` or `PT15M`), `bidding_zone`, `market`,
`source`, `source_file` and `document_id` (strings), `revision_number` (nullable integer)
and `document_created_at_utc` (nullable UTC timestamp). Each interval starts at `ts_utc`
and ends before `interval_end_utc`.

The hourly schema is `ts_utc` (`datetime64[ns, UTC]`) and `price_mean`, `price_min`,
`price_max` (float64, EUR/MWh). An hourly source observation becomes all three values.
At the [SDAC cutover](https://www.entsoe.eu/network_codes/cacm/implementation/sdac/) on
2025-10-01 00:00 Central European summer time (2025-09-30 22:00 UTC, 01:00 in Bucharest),
native prices switch to 15-minute intervals. The hourly row then uses the arithmetic mean,
minimum and maximum of its four equal-duration prices. The expected UTC grid comes from
the two Romanian local midnights, so spring and autumn DST days have 23 and 25 hours.

Example output from the snapshot:

| ts_utc | price_mean | price_min | price_max |
| --- | ---: | ---: | ---: |
| 2023-05-21 09:00Z | -0.41 | -0.41 | -0.41 |
| 2025-09-30 21:00Z | 108.33 | 108.33 | 108.33 |
| 2025-09-30 22:00Z | 97.2625 | 91.07 | 109.27 |

Malformed or nonfinite prices, duplicates, inconsistent currency or units, and timestamps
off the expected grid fail the run. Negative prices remain valid. By default missing
intervals fail validation; `--allow-gaps` retains observed native prices and omits hours
that lack one or more of their native prices. The XML parser decodes source-declared
[variable-size blocks (A03)](https://transparencyplatform.zendesk.com/hc/en-us/articles/30262342482961-CurveType-A01-vs-CurveType-A03)
within a period. The snapshot has no original block bounds, so its missing points stay
missing. No gap is interpolated across periods, source files or hours. Cached inputs are
reused. To refetch an XML response, remove the specific cached file and rerun the same
command.

Observed results for Romanian calendar dates 2023-01-01 through 2026-07-31:

- 52,070 / 53,276 native intervals (97.74%): 23,680 hourly and 28,390 quarter-hourly.
- 30,544 / 31,391 complete hours (97.30%). Of 847 missing output hours, 379 have partial
  quarter-hour coverage and 468 have zero observed prices.
- 800 negative native prices and 383 negative hourly means.
- The 2025-03-30 smoke sample had 23 / 23 hours, including five negative prices.

## Weather and ML handoff

Use `gridsense.config.WEATHER_POINTS` for the first model (Bucharest, Constanța, Craiova
and Timișoara). For the expanded experiment, use
`gridsense.config.TOP_20_WEATHER_POINTS`. Both mappings use the `weather_fc.location`
ID as the key and a WGS84 `(latitude, longitude)` pair as the value. Use those same IDs
when selecting or pivoting weather features. The price target is one value per hour for
the Romanian bidding zone.

The expanded catalog follows resident population by municipality in the
[2021 census, table 1.22](https://www.recensamantromania.ro/wp-content/uploads/2023/05/Tabel-1.22.xlsx).
It reuses the four coordinates from `WEATHER_POINTS` and uses
[Open-Meteo geocoding (GeoNames)](https://open-meteo.com/en/docs/geocoding-api) for the
other 16 cities.

Load the hourly table with `gridsense.io.read("prices_hourly")`. Join
`weather_fc.target_ts_utc` to `prices_hourly.ts_utc` as a many-to-one join. For training
targets, an inner join retains only complete labeled hours; for coverage analysis, use a
left join and inspect missing labels. Select the weather forecast by its issue date, lead
and location before pivoting to the feature table. Never use forward or backward filling
to create a label. For lag features, first construct the expected UTC grid or join on exact
timestamps. A row-based shift on a sparse table can use the wrong hour.

`price_mean` is the target. The target-hour mean/min/max become known when the corresponding
auction clears, so they cannot be inputs for that target before clearing. A delivery
timestamp says when electricity is delivered. `document_created_at_utc` is the XML
document creation time, which may reflect extraction or revision; it is not a verified
auction publication time. For the 10:00 Bucharest forecast, use only auctions known to have
cleared before issue time, with a conservative previous auction cutoff until publication
times and revisions are independently verified. The market delivery day follows CET/CEST
and starts at 01:00 in Bucharest; keep that distinction when deriving auction dates.

### Price features and weather join check

Call `gridsense.data.price_features.add_price_features(rows, prices)` with
`issue_ts` and `target_ts_utc` on the forecast rows, and the hourly price table.
The function requires the configured 10:00 Bucharest issue and a configured
future delivery day. It maps the target's local clock hour to issue day D and D−6,
then looks up the exact UTC delivery intervals. Missing, nonexistent or ambiguous
lag hours stay null.

The D midday mean and minimum require all four prices for 11:00–15:00 local.
The seven-day midday minimum and negative-hour count use observed prices from
D−7 through D−1. The matching coverage columns report the observed fraction of
expected hours, including DST. The day D features rely on the prior auction's
publication schedule. The snapshot does not establish which revisions were available
at the issue time.

With the local `prices_hourly.parquet` in place, run:

```bash
uv run python -m gridsense.data.check_weather_join
uv run python -m gridsense.data.check_weather_join --weather /path/to/weather_fc.parquet
```

The first command writes `weather_fc.synthetic.parquet` and
`price_weather_join.synthetic.parquet` under the ignored
`data/interim/weather_join_2025-03-30/` directory. The fixture has 92 synthetic
weather rows for four cities. After pivoting, the check requires one real price
label for each of the 23 UTC delivery hours on March 30 in Bucharest. The second
command checks the same issue and delivery day in a supplied file. The synthetic
outputs are integration fixtures.

## Rebuild from local ENTSO-E File Library exports

With the filtered `.csv.gz` extracts in `data/raw/entsoe_file_library/selected/`
and the existing Power Statistics `regional_load_hourly.parquet` in place, run:

```bash
uv run python -m gridsense.data.build_file_library
```

The build refreshes the existing Romanian and regional Parquet contracts through
the configured test end date. It keeps the pinned Power Statistics load on
overlapping hours and adds complete Romanian hours from the File Library. The
original `ActualTotalLoad_6.1.A_r3/` ZIP archives alongside `selected/` supply
Hungarian and Bulgarian load after the end of the Power Statistics release.
Subhourly prices and measurements require four distinct quarters per hourly
average. Bulgarian load uses the source's hourly values. The regional manifest
reports missing hours by country.

The normalized source tables live under `data/processed/entsoe_file_library/`.
They retain separate forecast updates, outage versions and segments, border
directions, and Germany–Luxembourg price sequences. Equal prices within the same
market sequence are collapsed to one observation. Each Parquet has a unique key
and a checksum listed in `manifest.json`.

`grid_actual_hourly.parquet` in that folder contains the historical hourly load,
solar and wind measurements. In the shared `grid_hourly.parquet`, each new
measurement from the File Library must have an update timestamp at or before
10:00 Bucharest time the day after delivery, when the current D−1 features use
it. The same check applies to new load for all three countries in the regional lag features.
The timestamp of the extract's recorded update can be later than the original
publication. Forecast and outage extracts remain separate from the model inputs.

## Regional market inputs from pinned public sources

Run the regional build from the repository root. The command uses pinned public
sources and works on a fresh checkout without an ENTSO-E token.

```bash
uv sync --locked
uv run python -m gridsense.data.build_regional
```

| File in `data/processed/` | Contract |
| --- | --- |
| `regional_prices_hourly.parquet` | One row per `bidding_zone` and `ts_utc`. RO, HU and BG, with `country_code` and the existing `price_mean`, `price_min`, `price_max` fields in EUR/MWh. |
| `regional_load_hourly.parquet` | One row per `country_code` and `ts_utc`. RO, HU and BG actual hourly system load (`load_actual_mw`, MW), with zone and source identifiers. |
| `regional_market_features.parquet` | One row per `issue_ts`, `target_ts_utc`, `horizon_days`, with 11 regional `f_*` columns. Left join on those keys with one-to-one validation. |
| `regional_market_manifest.json` | Input release pins, coverage and output SHA-256 checksums. |

RO is included in the regional prices for the spread calculation and as a reference
for labels. The existing `prices_hourly.parquet` remains the Romanian target contract.
The regional feature table has no labels. Use the normal chronological splits and
compare model variants on the same validation hours.

- **Prices.** The same pinned ENTSO-E snapshot used for RO supplies HU
  (`10YHU-MAVIR----U`) and BG (`10YCA-BULGARIA-R`). This build covers Romanian
  delivery dates 2023-01-01 through 2026-07-31. Keep complete hours only, using the
  native hourly observation or all four 15-minute prices. Negative prices are valid.
- **Load.** [ENTSO-E Power Statistics, Monthly Hourly Load Values](https://www.entsoe.eu/data/power-stats/)
  supplies national UTC observations from 2023-01-01 through 2026-06-30. Retain only
  `Cov_ratio = 100` and use `Value`. ENTSO-E's public files can be revised in place.
  The build checks each file against its release pin. If the publisher updates a
  file, use the original cached release or review the new release before updating
  its checksum.
- **Availability.** The issue clock is 10:00 in Bucharest. Use the target's
  Romanian clock hour to look up HU/BG prices and RO-minus-neighbor spreads on
  issue day D and D−6, from auctions already cleared under the project's timing
  policy. Use actual load from D−1 for each of RO/HU/BG, allowing for reporting
  delay. All legs of a spread use the same UTC hour. A missing or ambiguous
  interval stays null. Load lags beyond the pinned consumption coverage also stay
  null. Historical exports do not establish which revisions were visible at issue time.

**Team handoff.** The repository includes the processed regional tables, the
Romanian price and grid tables, their quality reports, and the baseline calendar
and training Parquet. Regenerate the baseline with
`uv run python -m gridsense.data.calendar` and `make features`. The training table
uses the calendar, Romanian prices, and grid lags. Normalized File Library
Parquets and their manifest are included under `data/processed/entsoe_file_library/`.
These tables are derived from ENTSO-E Transparency Platform extracts filtered to
the documented areas and period. Raw inputs and synthetic fixtures stay in
ignored directories. The source dataset card
uses `license: other` and refers users to the applicable ENTSO-E terms. The ENTSO-E
website's disclaimer also restricts redistribution of website content without
written permission, so the team needs to establish the applicable rights for these
derived datasets before any further redistribution.
[Dataset card](https://huggingface.co/datasets/hsilvosa/entsoe-day-ahead)
[ENTSO-E disclaimer](https://www.entsoe.eu/about/legal-and-regulatory/disclaimer/)

The team's `weather_hourly.parquet` follows `WEATHER_HOURLY` for historical
observations. The model's `weather_fc.parquet` follows `WEATHER_FC`
(`WEATHER_ARCHIVED_FC` is a compatibility alias) and requires forecast issue dates,
irradiance and 100 m wind. Observed weather is never substituted for future target
forecasts. The Romanian calendar can include country, working-holiday and split
metadata, while its core ML contract remains compatible with the original continuous
calendar. Working-holiday metadata uses the raw holiday CSV when present; the
core calendar also works without that ignored file. See the
[ML handoff](ml_handoff.md) for the archived-weather implementation and availability limits.

### Romanian grid table and regional join

For the pinned public-source build, run:

```bash
uv run python -m gridsense.data.build_grid
uv run python -m gridsense.data.check_regional_ml_join
```

`build_grid` uses Romanian rows from `regional_load_hourly.parquet` and writes the
shared `grid_hourly.parquet` contract through `gridsense.io.write`. The file has
UTC hourly timestamps and real load in MW. `solar_actual_mw` and `wind_actual_mw`
are null until corresponding measurements are collected. Missing load hours remain
absent. The command accepts an existing identical output and stops if the existing
file differs, so later generation data is preserved for reconciliation.

The join check calls the existing ML `build_training_table` with real prices and
load plus a synthetic weather and calendar fixture. It validates a D+1 forecast
for 2025-03-30, checks all 23 UTC hours and price labels, joins the regional table
on `issue_ts`, `target_ts_utc` and `horizon_days`, and verifies the RO load
features against D−1 measurements. Its output is the ignored
`data/interim/weather_join_2025-03-30/ml_regional_join.synthetic.parquet`.
Weather and calendar in that output are synthetic, and the file is an integration
fixture. The reusable `join_regional_features` helper checks key uniqueness and
returns both the left-joined table and the number of unmatched forecast keys.
The normal ML build does not yet call this helper.

Load hours are retained only when the original ENTSO-E coverage ratio is 100%.
The current ML daily mean groups the available hours; verify that each D−1 day is
complete before treating the mean as a complete-day statistic. Historical load
exports can contain later revisions, and their exact availability at a past issue
time has not been established.

## Optional grid signals

ENTSO-E documents the following sources in its
[REST API integration guide](https://transparencyplatform.zendesk.com/hc/en-us/sections/12783116987028-Restful-API-integration-guide).
Collect them separately from prices and keep their availability metadata.

| Signal | ENTSO-E dataset | Availability for a 10:00 Bucharest forecast |
| --- | --- | --- |
| National load | A65, A16 actual | Use historical lags with verified publication delay. The same public archive also has an `actual_load` table. |
| Load forecast | A65, A01 day-ahead | Use only a vintage independently verified to have been published by issue time. |
| Total generation | A75 actual by type; aggregate only with complete categories | Use lagged actuals; track missing production types and distinguish generation from consumption. |
| Solar and wind generation | A75 actual by type | Use lagged actuals; never join on future target time as a feature. |
| Total / wind / solar forecasts | A71 / A69 day-ahead | Require publication time and revision history before using at the 10:00 cutoff. |
| Cross-border physical flows | A11 actual | Use lagged values with directional border metadata; actual flows arrive after delivery. |
| Generation unit unavailability | A80 (TR 15.1), File Library `UnavailabilityOfProductionAndGenerationUnits_15.1.A_B_C_D_r3.1` | Planned and forced. Use only the latest version of each message published by issue time (`gridsense.data.outages.offline_mw_as_of`). |

Live grid acquisition and verification of forecast vintages are separate follow-up work.
