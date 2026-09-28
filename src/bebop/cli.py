from __future__ import annotations

import json
from pathlib import Path

import typer

from bebop.adapters.ao import AOClient
from bebop.models import TaskCapsule
from bebop.runtime import init_dbos
from bebop.workflow import execute_task

app = typer.Typer(no_args_is_help=True)


@app.command()
def projects() -> None:
    """List projects registered with the running Agent Orchestrator."""
    client = AOClient()
    try:
        for project in client.list_projects():
            state = "missing" if project.folder_missing else "ok"
            typer.echo(f"{project.id:20} {state:8} {project.name}  {project.path}")
    finally:
        client.close()


@app.command()
def run(task_file: Path) -> None:
    """Run one durable Bebop task through Agent Orchestrator."""
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    task = TaskCapsule.model_validate(payload)

    init_dbos()
    result = execute_task(task.model_dump())
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
