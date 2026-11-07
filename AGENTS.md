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
- If the column is one triggers can read, also update `Trigger.Column` and `Trigger.COLUMNS_OF` in
  `packages/shared/domain/Trigger/Trigger.ts`.
- `npm install --legacy-peer-deps` once (some npm versions fail on vitest's peers without it), then `npm test` and
  `npm run typecheck` before committing TypeScript changes.
- Style follows Quarry: a concept is a namespace with its zod `Schema` and its type declared after it
  (`export type Run = z.infer<typeof Run.Schema>`); ids are branded UUIDv7 (`Foundations.Id.define("X.Id")`);
  four-space indentation.
