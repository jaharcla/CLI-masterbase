from __future__ import annotations

import json
from pathlib import Path

import typer

from bebop.models import TaskCapsule
from bebop.runtime import init_dbos
from bebop.workflow import execute_task

app = typer.Typer(no_args_is_help=True)


@app.command()
def run(task_file: Path) -> None:
    """Start one durable Bebop task from a JSON TaskCapsule."""
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    task = TaskCapsule.model_validate(payload)

    init_dbos()
    result = execute_task(task.model_dump())
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
