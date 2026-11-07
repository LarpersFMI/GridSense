"""The PipelineRunner's way in.

    uv run python -m gridsense.pipelines list         # the pipelines, as JSON (Pipeline.Schema[])
    uv run python -m gridsense.pipelines run prices   # runs one; exits 1 if it raised
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback

# Each module registers its pipelines on import.
import gridsense.pipelines.demo  # noqa: F401
from gridsense.pipelines import REGISTRY, Run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("run").add_argument("name", choices=sorted(REGISTRY))
    args = parser.parse_args()

    if args.command == "list":
        print(json.dumps([pipeline.definition() for pipeline in REGISTRY.values()]))

        return

    try:
        REGISTRY[args.name].run(Run())
    except Exception:  # noqa: BLE001 - CLI boundary reports arbitrary pipeline failures and exits.
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
