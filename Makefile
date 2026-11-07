.PHONY: setup data fake-data features train predict evaluate agent app test lint

setup:
	uv sync

data:
	uv run python -m gridsense.data.build

# Use the fake tables for any later step with: GRIDSENSE_DATA=fake make features train ...
fake-data:
	GRIDSENSE_DATA=fake uv run python -m gridsense.synthetic.market

features:
	uv run python -m gridsense.features.build

train:
	uv run python -m gridsense.models.train

predict:
	uv run python -m gridsense.models.predict

# Scores validation by default; FINAL=1 scores the test set once.
evaluate:
	uv run python -m gridsense.models.evaluate $(if $(FINAL),--final,)

agent:
	uv run python -m gridsense.agent.run

app:
	uv run streamlit run app/streamlit_app.py

test:
	uv run pytest

lint:
	uv run ruff check src tests app
