# Agent instructions

Before changing code, read [README.md](README.md), especially "Rules for anyone (or any coding agent) working in this repo", [docs/project_plan.md](docs/project_plan.md) and, for agent, dashboard or chatbot work, [docs/agent_design.md](docs/agent_design.md).

- Use `uv run` for Python. Run `make test` and `make lint` before committing.
- Take split dates, thresholds and paths from `src/gridsense/config.py`, and parquet columns from `src/gridsense/schemas.py`.
- Never evaluate on the test split unless explicitly asked; tune on validation.
- Stay in your team's area (see "Team and ownership" in the README); flag schema changes instead of silently editing them.

## TypeScript packages (`packages/`)

The Watchdog, the agent, the server and the frontend are TypeScript (NestJS, BullMQ on Redis, React). Their shared
contracts are zod schemas in `packages/shared/domain/`, one namespace per concept: `Dataset`, `Forecaster`, `Time`,
`Trigger`, `Watchdog`, `Agent`, `Foundations`.

- **A schema change goes to both sides, in the same commit.** If you add, rename or remove a column, or change its type,
  in a parquet schema in `src/gridsense/schemas.py`, update its namespace in `packages/shared/domain/Dataset/` too
  (`PREDICTIONS` → `Dataset.Predictions`, `PRICES_HOURLY` → `Dataset.PricesHourly`). Columns keep their parquet names.
  A new dataset the TypeScript side reads gets its own file there.
- Triggers don't know columns: a condition names a dataset and a column, and the UI lists them from
  `Dataset.API.describe` (`GET /api/datasets/:name/schema`), which reads the parquet file itself. A column the file
  adds is one an admin can write conditions on, with nothing to change here. The row schemas are loose.
- Columns the Watchdog computes per hour (`local_hour`, `weekday`, …) are declared and computed next to their dataset:
  `Dataset.Predictions.COMPUTED_COLUMNS` and `compute`.
- **Run it:** `cp .env.example .env`, `npm run infra` (Postgres + Redis in Docker), then `npm run dev` (server on :4000,
  Watchdog on :4100). The server migrates on boot. Report a run like the Python pipeline will:
  `curl -XPOST localhost:4000/internal/runs -H 'content-type: application/json' -d '{"issueTs":"2026-05-07T07:00:00Z","modelVersion":"dummy-0","rows":168,"predictionsPath":"<absolute path to predictions.parquet>"}'`,
  and appended prices with `curl -XPOST localhost:4000/internal/datasets/prices/updates` — or from Python,
  `gridsense.report_dataset_updated`. Every run appends to the same predictions file in `DATASET_DIR`; each trigger
  reads its rows past its watermark on its incremental column (`issue_ts`, `ts_utc`).
- **The dummy week, live:** `DATASET_DIR=data/replay` in `.env`, then
  `uv run python -m gridsense.replay --from 2026-05-13 --to 2026-05-15 --create-triggers` — appends each day's run and
  the next day's prices, reporting each, with the demo triggers T1–T5 saved first.
- **How it runs, flow by flow:** `packages/docs/` — a run reported, a dataset update checked, a hit raised, schedules,
  the trigger editor, the agent, realtime. Update the page when you change its flow.
- Packages: `server` (owns Postgres, `/api` for the browser, `/internal` for workers and Python, `/socket` for live
  events), `watchdog` (BullMQ worker, no database: checks triggers, hands hits to the agent), `central-agent`, `frontend`.
- Common dependencies live in the root `package.json`; a package lists only what's its own. Compiler options come from
  `tsconfig.base.json`.
- `npm install --legacy-peer-deps` once (some npm versions fail on vitest's peers without it), then `npm test` and
  `npm run typecheck` before committing TypeScript changes.
- Style follows Quarry: a concept is a namespace with its zod `Schema` and its type declared after it
  (`export type Run = z.infer<typeof Run.Schema>`); ids are branded UUIDv7 (`Foundations.Id.define("X.Id")`);
  four-space indentation.
