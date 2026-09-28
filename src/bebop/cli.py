from __future__ import annotations

from pathlib import Path

import typer

from bebop.models import Task
from bebop.scheduler import Scheduler
from bebop.state import StateStore

app = typer.Typer(no_args_is_help=True, help="Bebop Code Hub")


def _store(root: Path) -> StateStore:
    return StateStore(root / ".bebop" / "state.db")


@app.command()
def init(root: Path = typer.Argument(Path("."))) -> None:
    """Initialize Bebop state in a repository."""
    store = _store(root)
    store.close()
    typer.echo(f"Initialized {root / '.bebop' / 'state.db'}")


@app.command()
def add_demo(root: Path = typer.Argument(Path("."))) -> None:
    """Add a tiny dependency graph for smoke testing."""
    store = _store(root)
    scheduler = Scheduler(store)
    scheduler.add_tasks(
        [
            Task(id="T001", title="Inspect repository"),
            Task(id="T002", title="Implement change", dependencies=["T001"]),
            Task(id="T003", title="Verify result", dependencies=["T002"]),
        ]
    )
    store.close()
    typer.echo("Added demo DAG: T001 -> T002 -> T003")


@app.command()
def tasks(root: Path = typer.Argument(Path("."))) -> None:
    """Show persisted tasks."""
    store = _store(root)
    scheduler = Scheduler(store)
    scheduler.refresh_ready()
    for task in store.list_tasks():
        typer.echo(f"{task.id:8} {task.status.value:12} {task.title}")
    store.close()


if __name__ == "__main__":
    app()
