# Romanian solar and wind generation handoff

`data/processed/renewable_generation_asof.parquet` is a supplementary table for
ML, keyed one-to-one by `issue_ts`, `target_ts_utc`, `horizon_days`. It contains
D−1 solar maximum of hourly means (`solar_daily_mw`) and wind mean of hourly
means (`wind_daily_mw`) over the previous **complete Romanian local calendar day**.
Each underlying quarter-hour
must be present and its latest recorded update must be at or before the 10:00
Bucharest issue. An incomplete hour or day leaves that fuel's statistic null.
The corresponding `*_updated_at_utc` records the latest contributing update,
while `*_known_hours` and `expected_hours` expose completeness, including
23- and 25-hour days. Preserve the existing ML training table and schema; join
this supplementary table using a validated one-to-one join. No label or
observed future generation is included.

**Training limitation:** the available File Library extract records only the
latest version for each quarter-hour. Zero training or validation forecast rows
have a complete D−1 solar or wind day with all recorded updates by issue time.
Do not use the retrospective values as a substitute, infer publication timestamps,
or evaluate an ablation on the basis of this table. The late timestamp does not
prove that an earlier value was unavailable; the extract does not establish the
earlier value. The source's update timestamps are treated as conservative
availability evidence, subject to ENTSO-E's timestamp semantics; they are not a
certified full as-issued archive. Missingness can reflect later revisions, so it
also must not be presented as a verified historical availability signal.

The source is the Romanian subset of `AggregatedGenerationPerType_16.1.B_C_r3`
from the authenticated ENTSO-E Transparency Platform File Library, already
stored as `data/processed/entsoe_file_library/generation.parquet`. The File
Library uses account credentials and does not require an API token. For a June
2024 source file, the Romanian subset of the original ZIP and the selected
extract were identical; the raw fields contain `UpdateTime(UTC)` but no separate
original publication timestamp. The platform's Value History for the sampled
2024-06-01 00:00 wind and 08:00 solar quarter-hours each showed only one
internal version, updated on 2025-10-13. This two-point check does not establish
whether all earlier histories are absent. The visible `TP_Legacy_Publications`
folder list did not include an aggregated-generation archive; file-level older
versions remain unverified. A third-party archive would need both proof of its
original capture time and the actual earlier values, not simply an old-looking
delivery date.

## Further historical-source investigation (2026-11-07)

The local ENTSO-E generation extract has 35,033 quarter-hour records for each
fuel in local year 2023 and 35,135 for each in 2024. The earliest recorded
update for either fuel is 2025-10-12 in both years. These are the earliest
timestamps in **our current extract**, not evidence of first publication. The
training split ends in February 2025 and validation ends in September 2025, so
even relaxing the complete-day rule cannot make these 2023–2024 values known
at an earlier issue time. The earliest recorded update for 2025 observations
is 2025-10-13, also after the validation period.

ENTSO-E documents [Value History](https://transparencyplatform.zendesk.com/hc/en-us/articles/33729752039441-Value-details-and-value-history)
as an overview of historical submissions accessible to registered users. The
two values inspected above are only a small sample; the documentation does not
prove complete legacy history or the availability of a bulk export. ENTSO-E's
[request-parameter documentation](https://transparencyplatform.zendesk.com/hc/en-us/articles/12783280128404-Request-Parameters-Time-Interval)
states that update-time filtering is available only for outages, so it is not
an established route to reconstruct generation vintages through the REST API.

[Monitor Energie](https://gravityresearch.eu/monitor-energie) describes an
archive of Transelectrica operational snapshots. On 2026-11-07, its public
`/v1/history` endpoint returned no points for 2023-06-01, 2024-06-01,
2025-06-01 or 2026-06-01 UTC when queried for hourly solar and wind. The same
request returned 24 hourly points for 2026-10-15, so the endpoint itself did
return data for a control day. These are samples, not a complete archive
survey. The hourly response included observation-hour, mean and sample count,
but no individual observation capture time or original ENTSO-E publication
time. Transelectrica operational measurements are also a separate source and
must not silently be treated as identical to ENTSO-E aggregated generation.
Example query:

```text
https://sen-api-3yueqnwriq-ew.a.run.app/v1/history?start=2024-06-01T00%3A00%3A00Z&end=2024-06-02T00%3A00%3A00Z&resolution=hour&metrics=wind_mw%2Csolar_mw
```

[Solar Industry Romania](https://solarindustry.ro/data-history) also offers
hourly averages of retained Transelectrica observations. Its 90-day endpoint
examined on 2026-11-07 contained observation hours and sample counts, without
per-reading capture timestamps. Its response also contained future-dated
records, so its temporal quality and archival provenance need independent
verification. Neither third-party response is a verified, point-in-time history
for the training or validation period; no records were added to model inputs.
The next useful lead is an archive that can supply the actual values and a
verifiable capture time before each issue, or confirmation from ENTSO-E that
older versions and their publication times are available. An H+1 regulatory
publication deadline alone does not prove when a particular value appeared.

To rebuild the handoff, run:

```bash
uv run python -m gridsense.data.renewable_generation_asof
```

The command checks source timestamps, keys and coverage and refuses to replace
existing differing handoff files unless `--replace-existing` is passed after
review. Its companion manifest records the input and
output hashes, row count and train/validation availability. Raw File Library
extracts stay in ignored local storage. No test-set metrics are computed.
