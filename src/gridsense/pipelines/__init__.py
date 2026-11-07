"""Pipelines: the Python that keeps the datasets in DATASET_DIR up to date, run by the PipelineRunner.

A pipeline is a function, registered with @pipeline. Its schedule is not here: the UI sets it (Pipelines page) and
the PipelineRunner runs it — `python -m gridsense.pipelines run <name>` — on that schedule or when asked.

    @pipeline("prices", "Appends the next day's cleared prices.", outputs=["prices"], default_cron="15 14 * * *")
    def prices(run: Run) -> None:
        rows = ...                                   # whatever is new
        run.append("prices", rows, key=["ts_utc"])  # written, then reported: the Watchdog checks the triggers on it

A new pipeline shows up in the UI switched off, with default_cron as its schedule, the next time the
PipelineRunner starts. What it prints is the run's log, live in the UI. It fails by raising.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gridsense.pipelines.store import Run

__all__ = ["Pipeline", "REGISTRY", "Run", "pipeline"]


@dataclass(frozen=True)
class Pipeline:
    """As the PipelineRunner sends it to the server (Pipeline.Schema): name, description, outputs, defaultCron."""

    name: str
    description: str
    outputs: list[str]
    default_cron: str
    run: Callable[[Run], None]

    def definition(self) -> dict:
        return {
            "name":        self.name,
            "description": self.description,
            "outputs":     self.outputs,
            "defaultCron": self.default_cron,
        }


REGISTRY: dict[str, Pipeline] = {}


def pipeline(name: str, description: str, *, outputs: list[str], default_cron: str) -> Callable:
    """Registers the function as a pipeline. name: lowercase, digits and dashes. default_cron: five fields, Romanian time."""

    def register(function: Callable[[Run], None]) -> Callable[[Run], None]:
        if name in REGISTRY:
            raise ValueError(f"Two pipelines named {name}")

        REGISTRY[name] = Pipeline(name, description, outputs, default_cron, function)

        return function

    return register
