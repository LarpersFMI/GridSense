# Handoff: GridSense TypeScript side (written 7 Nov 2026, evening)

Context dump for the next Claude session, which continues the work. Read this file first, then `AGENTS.md` and `packages/docs/`.

## Who, what, deadline
- SmartHack XI 2026, the PPC challenge. Code freeze is **Sunday 8 Nov at 12:00**; the demo starts at 13:00 (5 minutes, plus 2 minutes of technical questions).
- GridSense forecasts zero- or negative-price hours on the Romanian day-ahead market. An agent then announces, confirms or cancels free-hour slots for customers, with a human approving the uncertain cases.
- The user (Roland) owns the TypeScript side: server, Watchdog, PipelineRunner, central agent and frontend. Teammates own the Python data and ML; the real model code lives elsewhere, and the repo has mostly stubs plus dummy/synthetic data.
- The user writes in Romanian or English. Answer in the language of their last message; earlier in this session it was Romanian.

## Rules the user insisted on (keep them)
- **Work directly in the user's repo**, `/Users/rolandteslaru/Desktop/GridSense` (from device_bash: `$HOME/mnt/Desktop/GridSense`). Never use a container copy.
- **Never `npm install` from the Linux VM**: it installs Linux native binaries into the Mac's `node_modules`. Add the dependency to `package.json` and ask the user to run `npm install --legacy-peer-deps` on the Mac.
- `npx tsc --noEmit -p packages/<pkg>` works from the VM. vitest does not (darwin rollup binary). Python tests run in the VM with `PYTHONPATH=src python3 -m pytest tests -p no:cacheprovider`. Never `uv run` in the VM: it would create a Linux `.venv` in the repo.
- Discuss namespaces and schemas with the user before coding something new. Don't commit unless asked.
- **Quarry style:**
  - one namespace per concept, a zod `Schema` with the type declared after it, and `index.ts` re-exporting;
  - 4-space indent;
  - Records keyed by id;
  - no private helper methods in services;
  - no defensive noise.
- **Quotes and semicolons:**
  - server and workers: single quotes, semicolons;
  - `shared/domain`: double quotes, no semicolons;
  - frontend: single quotes, no semicolons.
- **Frontend:**
  - Blueprint for controls, Tailwind for layout.
  - Blueprint's unlayered CSS beats Tailwind utilities on the same element. Size controls through a wrapper div, or write specific CSS in `index.css` (e.g. `table.bp6-html-table.pipelines-table td`).
  - Blueprint sets `form { display: block }`, so lay a form out through an inner div.
  - There is no Tailwind preflight, so native `<button>` and `<textarea>` keep browser styles. Use Blueprint components, or `div role=button`.
  - Use `Tabs` (`components/Choice.tsx`) only for fixed sets of 2–3 short options. Use `components/Dropdown.tsx` (PopoverNext, arrow, scale animation) for lists that may grow or have long labels.
  - Blueprint Table renderers must return `Cell` / `ColumnHeaderCell` directly.
- The user likes short answers, visuals over long markdown, and verifying in the built-in browser (http://127.0.0.1:5173 from the Mac).

## Architecture (npm workspaces `packages/*`)
| Package | Port | What |
|---|---|---|
| `shared` | | `domain/` (zod and types, double quotes) and `server/` (queue, realtime, redis, system log, internal-api) |
| `server` | 4000 | NestJS, Postgres via Kysely (migrations in `packages/server/migrations`, applied on boot), `/api` for the browser, `/internal` for workers and Python, `/socket` for realtime (Redis pub/sub relay) |
| `watchdog` | 4100 | BullMQ worker. On `Dataset.Update` it evaluates triggers past their watermark and puts hits on `agent.handle-hit` (job id = thread id) |
| `pipeline-runner` | 4200 | Built this session (below) |
| `central-agent` | 4300 | **In progress** (below) |
| `frontend` | 5173 | React 19, Vite 7, Blueprint 6, Tailwind 4, TanStack Router and Query, Zustand + Immer, tsyringe SDK pattern |

- `npm run dev:all` starts docker (postgres, redis), then all of the above via concurrently.
- `.env` has `DATASET_DIR=data/fake`.
- Python lives in `src/gridsense`.

## Done this session
1. **Pipelines** (`packages/docs/pipelines.md` documents them).
   - Domain: `Pipeline` (Name, Schema, Schedule, Run, Event, API, API.Internal) and `PipelineRunner.Queue` (RunPipeline, Reconcile).
   - Server: migration `004_pipeline.sql` and `services/Pipeline`. `GET /api/pipelines` returns `nextRuns`, read from the BullMQ job schedulers.
   - Worker `packages/pipeline-runner`:
     - on boot it runs `python -m gridsense.pipelines list`, syncs the definitions, then reconciles the schedulers;
     - each run is a Python subprocess with its log streamed live;
     - the `@@gridsense {"rowsAppended":…}` marker is parsed by `src/services/python-output.ts`.
   - Python `src/gridsense/pipelines/` (`__init__` with the `@pipeline` registry, `store.Run.append`, `__main__`, `demo.py`):
     - `Run.append` writes atomically, dedupes on its key, then reports to the server (`report_run` / `report_dataset_updated`);
     - demo pipelines `prices` and `forecast` take the next day from the synthetic dummy data, DST-safe.
   - Tests: `tests/test_pipelines.py` (15 pass) and `packages/pipeline-runner/src/services/tests/python-output.test.ts`.
   - UI: Pipelines page (tab order: Pipelines, Datasets, Triggers, Activity), editable cron, on/off switch, Run now, runs with live log, countdown via `NextRun.tsx`.
2. **Dataset sidebar** (`features/datasets/DatasetSidebar.tsx`): Triggers and Pipelines tabs (48px tall). The Pipelines tab lists the pipelines writing the dataset, with a countdown, runs and log. The dataset preview refreshes live after a Watchdog check.
3. **Trigger templates** (`features/triggers/templates.ts` and `TemplatePicker.tsx`): Zero-cost window, Forecast dropped, Degraded data, Evening scarcity, Forecast miss, Negative prices cleared.
4. **Trigger editor as a wizard** (`TriggerEditor.tsx`, `components/Steps.tsx`):
   - steps: Name & description, When it runs, Conditions, Hits;
   - the Enabled switch is gone (new triggers are enabled; turn them off from the card);
   - section boxes removed; `textarea` font fixed in `index.css`.
5. **Simulation running on the user's Mac:**
   - `data/fake` was reset to start on 13 May 2026; the originals are in `data/fake/before-simulation/`;
   - 5 triggers were created through the API: Zero-cost window, Forecast dropped, Forecast miss, Degraded data, Negative prices cleared. The user also has an older trigger, "Zero cost window", on `price_p10`; it is noisy;
   - `forecast` runs on cron `0-58/2 * * * *` and `prices` on `1-59/2 * * * *`, both enabled, so one simulated day passes every 2 minutes. Turn them off in Pipelines when done;
   - hits pile up as `waiting` in `agent.handle-hit` because no agent consumed them yet.

## In progress: the central agent with LangGraph (user wants LangGraph so the graph is visible in the UI)
The user already ran `npm install` on the Mac, so `@langchain/langgraph` 1.7.2, `-checkpoint-postgres` 1.1.2, `@langchain/core`, `@langchain/anthropic` and `mermaid` 12.3 are installed. The package name stays `central-agent` and the domain stays `Agent`. Don't call it "AIP": the user was joking, that's Palantir's name.

### Done (all typecheck OK: shared, server, central-agent)
- **`shared/domain/Trigger/Playbook.ts`**: `Trigger.Playbook` = `announce-slot | confirm-slot | cancel-slot | alert`, with `DESCRIPTIONS`. `Trigger.Schema.playbook` defaults to `"alert"`. The server trigger repository maps the `playbook` column.
- **`shared/domain/Agent/`**:
  - `Decision` (label `confirmed | likely | possible | cancel | alert | none`, confidence, needsReview, rule, reason, inputs, window — the hours it kept —, followUps — the hours it sent on to their own threads);
  - `Action` (type, audience, title, text, wordedBy `llm | template`, at);
  - `Slot` (key = window key, start, end, label, status `announced | confirmed | cancelled`, threadIds, reason);
  - `Thread` (id = hit thread id, triggerId, playbook, status, hit, decision, actions, steps[{node, at, summary, data}], review, timestamps);
  - `Graph` {mermaid, nodes};
  - `Event`, rewritten: `agent:thread:updated {thread}` on `agent:threads`, `agent:slot:updated {slot}` on `agent:slots`. The old review events are gone; `tests/Event.test.ts` was updated;
  - `api/index.ts`: listThreads, getThread, review (POST, queues `agent.resume`), listSlots, getGraph, `CALENDAR_PATH /api/agent/calendar.ics`;
  - `api/internal.ts`: saveThread (PUT, upsert), getThread, listSlots (overlapping start/end), saveSlot, saveGraph.
- **Server:**
  - migration `005_agent.sql`: trigger.playbook column, plus tables `agent_thread`, `agent_slot`, `agent_graph`;
  - `services/Agent`: repository, service (emits realtime events, the review checks `awaiting-review`, generates the `.ics`), HTTP and internal controllers;
  - `AgentModule` is registered in `server.module.ts`.
- **`packages/central-agent`:**
  - `package.json`, `tsconfig.json`, `src/load-env.ts`, `main.ts` (port `AGENT_PORT` 4300);
  - `config.ts`: likelyMinP 0.8, possibleMinP 0.7, likelyMinHours 3, decideWithinDays 2, pilotCustomers 5000, shiftedMwhPerSlot 11.8, pilotIntervalHours 4, eveningPriceEur 140;
  - `graph/state.ts`: LangGraph `Annotation` state; actions and steps append;
  - `graph/decide.ts`: deterministic rules per playbook, reading `hit.evidence` keys like `predictions.p_near_zero.min/mean`, `prices.price_mean.mean`, `predictions.data_quality=ok`;
  - `graph/words.ts`: the template text, reworded by ChatAnthropic if `ANTHROPIC_API_KEY` is set, with fallback to the template;
  - `graph/graph.ts`: `StateGraph` load → decide → (act | review | dismiss); review → (act | dismiss). `review` uses `interrupt()`; resume with `Command({resume:{decision, note}})`. Every node is wrapped in `recorded()`, which saves the thread (`status running`) to the server so the UI follows live. `act` writes slots (announce, confirm, cancel) and worded actions;
  - `graph/agent-graph.service.ts`: `PostgresSaver.fromConnString(DATABASE_URL, {schema:'langgraph'})` plus `setup()`. On init it saves the mermaid graph (`getGraphAsync().drawMermaid()`). `handle`, `resume`, `settle` (`snapshot.next.length > 0` means `awaiting-review`, otherwise `acted` if there are actions, else `dismissed`), and `fail`;
  - processors: `handle-hit.processor.ts` (concurrency 1, threadId = job id) and `resume.processor.ts`;
  - `central-agent.module.ts`.
- **Root:** `package.json` has `dev:central-agent`, `dev` includes `agent`, and `typecheck` includes central-agent. `.env` and `.env.example` gained `AGENT_PORT=4300`, `ANTHROPIC_API_KEY=` and a commented `AGENT_LLM_MODEL`.

### Next steps (in order)
1. **Set playbooks on the simulation triggers BEFORE the agent starts.** Otherwise the queued hits get the default `alert`. The server must have restarted, so migration 005 has run. `PUT /api/triggers/:id` with the whole trigger plus `playbook`:
   - Zero-cost window → `announce-slot`
   - Forecast dropped → `cancel-slot`
   - Forecast miss → `cancel-slot`
   - Negative prices cleared → `confirm-slot`
   - Degraded data → `alert`
   - The user's older "Zero cost window" → `alert`, or ask the user. It's noisy; maybe disable it.

   Ask the user before using the browser tool: they rejected the last call (they were pausing for usage, not refusing).
2. **The user restarts `npm run dev`** so the `[agent]` process starts. Check that `/api/agent/graph` returns mermaid and that threads appear (`GET /api/agent/threads`).
3. **Frontend, task #23:**
   - `SDKs/AgentSDK`: state threads, slots and graph; watch `agent:threads` and `agent:slots`; actions list, get, review, slots, graph.
   - New navbar section **Agent** (icon e.g. `predictive-analysis`):
     - an Inbox (threads with status `awaiting-review`) with Approve and Reject plus a note;
     - a threads list;
     - a thread detail: the mermaid graph with the nodes it visited highlighted (append `classDef done fill:#2d72d2,color:#fff` and `class load,decide done` to the mermaid string, render with `mermaid.render`), plus the step log, the decision (rule, inputs, confidence, EV) and the actions (texts, wordedBy);
     - a Slots tab or calendar with a download link to `/api/agent/calendar.ics`.
   - **Wizard 5th step "Agent":** a Dropdown of `Trigger.Playbook` with its descriptions.
   - `draft.ts`: `createDraft` must set `playbook: 'alert'`. The `Trigger` type now requires it, so check the frontend typecheck.
   - Templates must set playbooks: Zero-cost window and Evening scarcity → announce-slot / alert; Forecast dropped and Forecast miss → cancel-slot; Negative prices cleared → confirm-slot; Degraded data → alert.
   - Add `playbook` to `STEP_FIELDS` in `TriggerEditor`.
4. **Run it end to end in the browser:** a Likely slot is announced automatically, a Possible one goes to the inbox, approving it acts, and Forecast miss cancels an announced slot through review.
5. **Docs:** rewrite `packages/docs/handling-a-hit.md` (no longer "planned"); add the agent to `AGENTS.md` and `packages/docs/realtime.md` (channels `agent:threads`, `agent:slots`).
6. **Optional, for the demo:** a one-command reset script (restore `data/fake` to 13 May, recreate triggers, clear `agent_*` tables, langgraph checkpoints and queues) so the demo can be rehearsed. A real demo week plus the real model predictions replace the dummy data later (teammates).

### Risks to check when it first runs
- **LangGraph checkpoint serde:** dates come back as strings. The code re-parses `hit`, `slots` and `trigger` with zod in the nodes, and `toThread` coerces. Watch for errors.
- **`interrupt()` re-runs the review node from the top on resume.** Nothing runs before `interrupt` in it, which is intended.
- **`getGraphAsync().drawMermaid()`:** if it fails, wrap it so the agent still boots.
- **The default model name `claude-haiku-5-5`** is only used when `ANTHROPIC_API_KEY` is set.
- **About 50 old waiting hits** will be processed at startup, one at a time (concurrency 1).
- **Thread IDs contain `:`/`_`:** URLs use `encodeURIComponent`.

## Demo plan (proposed to the user)
| Time | What |
|---|---|
| 0:00–0:30 | Problem |
| 0:30–1:30 | ML slides (data, baseline vs model, calibration) |
| 1:30–2:15 | Pipelines: Run now `forecast`, rows appear |
| 2:15–3:00 | Hits, then the agent thread on its graph, the inbox, approve, the notification |
| 3:00–3:45 | `prices` runs, Forecast miss, the slot is cancelled |
| 3:45–4:30 | Robustness: turn off a pipeline, degraded data, the agent becomes conservative |
| 4:30–5:00 | Impact and EU AI Act (human in the loop, decision log) |
  §
## Decided 8 Nov, ~00:45: the agent's thresholds (τ)
From the ML team's validation slot curve (`reports/real/eval/classify_slots_val.csv`, calibrated `lgbm_classifier`,
2–6 h blocks 09–18 where every hour has p ≥ τ): τ 0.7 → 71 % of slots hit, τ 0.8 → 80 %.
- Likely (announced automatically): **every hour p_near_zero ≥ 0.8** (min over the window).
- Possible (human review): **every hour 0.7 ≤ p < 0.8**.
- Zero-cost window trigger: p_near_zero ≥ 0.7 (done in the DB and in `templates.ts`).
- When the agent comes back from the stash: `config.ts` likelyMinP 0.85 → 0.8; `decide.ts` Possible from
  `meanP >= possibleMeanP (0.7)` to `minP >= 0.7`. Sent to Andrei for the final config.
- Demo plan: the validation replay (24 Apr – 5 May 2025) is the main one; a 2026 test week only if the single test
  evaluation and the refit are done before 12:00 (then ALLOW_TEST_REPLAY=1, and drop `data_quality = ok` from the
  trigger: test rows have no weather, all degraded).
