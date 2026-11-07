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

Live grid acquisition and verification of forecast vintages are separate follow-up work.
