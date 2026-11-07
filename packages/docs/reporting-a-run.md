# Reporting a run

`POST /internal/runs` — from the Python pipeline, once a run's predictions are fully written to their parquet file.

```jsonc
{
  "issueTs":         "2026-05-13T07:00:00Z",                 // when the forecast was made; one run per issueTs
  "modelVersion":    "lgbm-2026-05-10",
  "rows":            168,                                    // forecast hours written
  "predictionsPath": "data/processed/predictions.parquet"    // for the record: every run appends to this one file
}
```

`Forecaster.API.Internal.ReportRun` (`shared/domain/Forecaster/api/internal.ts`): request is `Forecaster.Run.Report`, response `{ run }`. From Python: `gridsense.report_dataset_updated.report_run(path, model_version)`.

## The flow

Reporting is the run's **completion notice**: the file may be written in pieces, so the Watchdog only reads it once Python says it's done. It's idempotent on `issueTs` — a pipeline that retries the call after a timeout gets the same run back, and nothing is queued twice.

```mermaid
sequenceDiagram
    autonumber
    participant P as Python pipeline
    participant S as ForecasterService
    participant DB as RunRepository (Postgres)
    participant Q as watchdog.dataset-updated (BullMQ)
    participant R as Redis pub/sub

    P->>P: write predictions parquet (issue_ts = T)
    P->>S: POST /internal/runs { issueTs: T, … }<br/>ReportRun.Request — 400 if malformed
    S->>DB: report(report)
    DB->>DB: insert … on conflict (issue_ts) do nothing
    alt already reported
        DB-->>S: { run, created: false }
        S-->>P: 201 { run } — nothing else happens
    else new
        DB-->>S: { run, created: true }
        S->>Q: add { dataset: predictions }
        S->>R: forecaster:run:reported { run } on forecaster:runs
        S-->>P: 201 { run }
    end
```

From here the Watchdog takes over: [checking-an-update.md](checking-an-update.md).

## What gets created

| Where | What |
|---|---|
| `gridsense.run` | `id` (UUIDv7, server-made), `issue_ts` (unique), `model_version`, `row_count`, `predictions_path`, `reported_at` |
| `watchdog.dataset-updated` | one job `{ dataset: "predictions" }`: each trigger on it reads the rows past its watermark — this run's |
| `forecaster:runs` | `forecaster:run:reported { run }` — the dashboard's run list updates live |

## Why the server queues it, not Python

- Python only has to speak HTTP + JSON, not BullMQ's job format.
- The run has to be in Postgres anyway: the dashboard lists runs, and every hit names the run its forecast came from (`GET /internal/runs?issueTs=`). Saving and queueing in one place keeps them in step.
- A queue rather than pub/sub: if the Watchdog is down, the job waits.

## Reading runs

| Endpoint | For | Returns |
|---|---|---|
| `GET /api/runs?limit=` | the dashboard | newest first |
| `GET /internal/runs?issueTs=` | `HourService.forNewRows` | the run whose rows have that `issue_ts`, or `null` |
| `GET /internal/runs/:id` | the agent | the run, 404 if none |
