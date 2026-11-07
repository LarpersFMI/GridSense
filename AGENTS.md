# Agent instructions

Before changing code, read [README.md](README.md), especially "Rules for anyone (or any coding agent) working in this repo", [docs/project_plan.md](docs/project_plan.md) and, for agent, dashboard or chatbot work, [docs/agent_design.md](docs/agent_design.md); for ML work, [docs/ml_plan.md](docs/ml_plan.md).

- Use `uv run` for Python. Run `make test` and `make lint` before committing.
- Take split dates, thresholds and paths from `src/gridsense/config.py`, and parquet columns from `src/gridsense/schemas.py`.
- Never evaluate on the test split unless explicitly asked; tune on validation.
- Stay in your team's area (see "Team and ownership" in the README); flag schema changes instead of silently editing them.
