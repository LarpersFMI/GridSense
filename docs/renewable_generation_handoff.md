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

To rebuild the handoff, run:

```bash
uv run python -m gridsense.data.renewable_generation_asof
```

The command checks source timestamps, keys and coverage and refuses to replace
existing differing handoff files unless `--replace-existing` is passed after
review. Its companion manifest records the input and
output hashes, row count and train/validation availability. Raw File Library
extracts stay in ignored local storage. No test-set metrics are computed.
