# Frontend

`packages/frontend` — the admin's UI: React 19 + Vite, Blueprint for controls, Tailwind for layout (no preflight, so Blueprint's styles stay). It follows Quarry's frontend patterns (Quarry `AGENTS.md` §2–9), without Quarry's shell, AppKit or dialogs: one small app, two pages.

```sh
npm run dev            # server, watchdog and the frontend on http://127.0.0.1:5173 (Vite proxies /api and /socket to :4000)
```

| Route | Page |
|---|---|
| `/datasets/$name` (home) | the dataset viewer: the file's latest rows on the left (newest first, refreshed when the Watchdog checks the dataset); the triggers on it, and their editor, on the right |
| `/triggers` | every trigger: what it watches, its conditions, its hits so far, an on/off switch |
| `/triggers/new`, `/triggers/$id` | the editor: dataset and incremental column, conditions from `Dataset.API.describe`, grouping, cooldown |
| `/activity` | the hits (from the agent's queue, then live) with their evidence; the live feed of runs and checks |

## SDKs

`src/SDKs/` — Quarry's pattern: each SDK is a named singleton (`@SDK('Trigger')`, `SDKManager`, tsyringe) extending `BaseSDK` — a Zustand + Immer store, its TanStack Query `query` object, and `useWith(selector, query => [...])` for components. Actions are `ActionGroup` classes in `actions/`, one file per group; a write logs, toasts (`NotificationSDK`) and rethrows.

| SDK | Store | Queries | Actions |
|---|---|---|---|
| `TriggerSDK` | `triggers` by id | `triggers`, `trigger(id)` | `trigger.list · get · create · update · setEnabled · remove` |
| `DatasetSDK` | — (read-only, one screen: cache only) | `describe(name)`, `preview(name, orderBy)` | `dataset.describe · getPreview`, `dataset.watch()` (invalidates a dataset's previews on each check of it); `ui/DatasetPreview` |
| `ForecasterSDK` | `runs` by id | `runs` | `run.list`, `run.watch()` (`forecaster:runs`) |
| `WatchdogSDK` | `hits` by thread id, `checks` (live only) | `hits` (`GET /api/hits`) | `hit.list`, `live.watch(triggerIds)` (`watchdog:activity`, `watchdog:trigger:<id>`) |
| `RealtimeSDK` | `isConnected` | — | `connect()`, `subscribeToChannel(channel, Schema, listener)` — every event parsed with its zod schema |
| `QuerySDK`, `NotificationSDK` | — | — | the one QueryClient; Blueprint toasts |

**Tabs or a dropdown.** Tabs (`components/Choice.tsx`, Blueprint's `Tabs`) are for a fixed set of two or three short options that will stay that set: the app's sections in the navbar (driven by the URL), a trigger's "when it's checked" (a dataset or a schedule), all/any. A list that will grow — datasets, columns, operators — or long labels (how hits are grouped) go in a dropdown (`components/Dropdown.tsx`).

**Fields one per row**, label on the left: `FormGroup inline` inside a `div.field-rows` (index.css gives every label in it the same width), as in the trigger editor's "when it's checked".

**Dropdowns** are `components/Dropdown.tsx`: a Blueprint `PopoverNext` (floating-ui) with a `Menu`, scaling in from its button — never a native `<select>`, and never Blueprint's older `Popover`, which places its content wrong under React 19. Lists over 8 options get a filter.

**Tailwind next to Blueprint:** Tailwind's utilities are in a CSS layer and Blueprint's styles aren't, so on the same element Blueprint wins (`bp6-fill` beats `w-60`). Size a Blueprint control from a wrapping `div`. The same goes for plain elements Blueprint styles: its `form { display: block }` beats `flex` on a `<form>`, so a form lays out through a `div` inside it.

The shell (`routes/__root.tsx`) keeps the live feeds open on every page: runs, checks, and every trigger's hits.

Every request and event goes through `@gridsense/shared/domain` (`Trigger.API`, `Dataset.API`, `Forecaster.API`, `*.Event`): the same zod schemas as the server. The editor validates with `Trigger.Schema` itself (react-hook-form + `zodResolver`).

## The dataset viewer

`GET /api/datasets/:name/preview?limit=&orderBy=` (`Dataset.API.GetPreview`) reads the file in `DATASET_DIR` with DuckDB: the latest `limit` rows (200 here), newest first by `orderBy` — a timestamp column, by default the file's first (`issue_ts`: the newest run first, its hours in order; `ts_utc` for prices) — and the total row count. Only the file's columns: the computed ones exist per hour, in the Watchdog. It's a plain read of the parquet, nothing more — no versions or transactions.

`DatasetSDK/ui/DatasetPreview.tsx` shows it in Blueprint's table (`@blueprintjs/table`, `Table2`): it scrolls and virtualizes itself and fills its parent, which needs a height. Its renderers must return `Cell` and `ColumnHeaderCell` themselves — the table clones them to place them, so a component of ours around them loses their `style` and the headers drift from their columns. A dataset with no file yet in `DATASET_DIR` is a 404 that says to run the pipeline or the replay. Headers are Foundry's: the name over its type (`Timestamp`, `Number`, `String`), and the table's own header menu (`menuRenderer`, always visible) — "Newest first by this column" orders the preview by a timestamp column. A control of ours inside the header's name can't be clicked: the table's selection layer sits over it.

## Hits

The hits come from `GET /api/hits` (`Trigger.API.ListHits`): the server reads them from the agent's BullMQ queue (`agent.handle-hit`), with each job's status (`waiting` until the agent exists). Nothing else stores hits; the queue keeps the last 1000.

## Trying it

1. `DATASET_DIR=data/replay` in `.env`, `npm run infra`, `npm run dev`.
2. `uv run python -m gridsense.replay --from 2026-05-13 --to 2026-05-15 --step` — writes what was known on the 13th and waits.
3. In the UI, create a trigger (or start the replay with `--create-triggers` for T1–T5).
4. Press Enter in the replay's terminal: each step appends a run (10:00) or a day's prices (14:00); the Activity page shows the checks and hits as they happen. On 15 May's auction, a "forecast miss" trigger (`predictions.p_near_zero ≥ 0.7`, `prices.price_mean > 20`, on `prices`) hits Saturday 16, 10:00–15:00.
