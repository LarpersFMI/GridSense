.PHONY: setup data features train evaluate agent app test lint

setup:
	uv sync

data:
	uv run python -m gridsense.data.build

features:
	uv run python -m gridsense.features.build

train:
	uv run python -m gridsense.models.train

evaluate:
	uv run python -m gridsense.models.evaluate

agent:
	uv run python -m gridsense.agent.run

app:
	uv run streamlit run app/streamlit_app.py

test:
	uv run pytest

lint:
	uv run ruff check src tests app
