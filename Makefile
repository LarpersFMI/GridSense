.PHONY: setup data weather fake-data fake-predictions features train predict evaluate agent app test lint overnight-prepare overnight-smoke overnight

setup:
	uv sync

data:
	uv run python -m gridsense.data.build

# Archived forecast offsets; defaults to train + validation, not the test period.
weather:
	uv run python -m gridsense.data.weather $(if $(filter 1,$(EXTRA)),--extra --pace-seconds 60,)

# Use the fake tables for any later step with: GRIDSENSE_DATA=fake make features train ...
fake-data:
	GRIDSENSE_DATA=fake uv run python -m gridsense.synthetic.market

# Fake predictions for the agent/demo teams (test period by default).
fake-predictions:
	GRIDSENSE_DATA=fake uv run python -m gridsense.synthetic.predictions

features:
	uv run python -m gridsense.features.build $(if $(filter 1,$(REGIONAL)),--regional,) $(if $(filter 1,$(WEEK_AHEAD)),--week-ahead,) $(if $(filter 1,$(WEATHER_EXTRA)),--weather-extra,)

# TASK=classify or TASK=price trains one model only.
train:
	uv run python -m gridsense.models.train $(if $(TASK),--task $(TASK),)

predict:
	uv run python -m gridsense.models.predict

# Scores validation by default; FINAL=1 scores the test set once.
evaluate:
	uv run python -m gridsense.models.evaluate $(if $(TASK),--task $(TASK),) $(if $(FINAL),--final,)

agent:
	uv run python -m gridsense.agent.run

app:
	uv run streamlit run app/streamlit_app.py

test:
	uv run pytest

lint:
	uv run ruff check src tests app

# Isolated validation-only snapshots/jobs. Explicit RUN_DIR is required; no production training.
overnight-prepare:
	@test -n "$(RUN_DIR)" || (echo "RUN_DIR is required"; exit 1)
	GRIDSENSE_DATA=real uv run python -m gridsense.models.overnight --prepare --run-dir "$(RUN_DIR)" $(if $(PROFILES),--profiles $(PROFILES),) $(if $(VARIANTS),--variants $(VARIANTS),)

overnight-smoke:
	@test -n "$(RUN_DIR)" || (echo "RUN_DIR is required"; exit 1)
	GRIDSENSE_DATA=real uv run python -m gridsense.models.overnight --smoke --run-dir "$(RUN_DIR)"

# caffeinate keeps this macOS machine awake for the lifetime of the sequential queue.
overnight:
	@test -n "$(RUN_DIR)" || (echo "RUN_DIR is required"; exit 1)
	GRIDSENSE_DATA=real caffeinate -i uv run python -m gridsense.models.overnight --execute --run-dir "$(RUN_DIR)"
