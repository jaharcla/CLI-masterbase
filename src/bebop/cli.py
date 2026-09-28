from __future__ import annotations

import json
from pathlib import Path

import typer

from bebop.adapters.ao import AOClient
from bebop.models import GoalPlan, TaskCapsule
from bebop.planner import plan_goal
from bebop.repo_context import build_repo_context
from bebop.runtime import init_dbos
from bebop.workflow import execute_goal, execute_task

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


@app.command("run-plan")
def run_plan(plan_file: Path) -> None:
    """Execute a validated dependency graph of Bebop tasks."""
    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    plan = GoalPlan.model_validate(payload)

    init_dbos()
    result = execute_goal(plan.model_dump())
    typer.echo(json.dumps(result, indent=2))


def _create_plan(goal: str, project: str) -> GoalPlan:
    client = AOClient()
    try:
        ao_project = client.resolve_project(project)
    finally:
        client.close()

    context = build_repo_context(ao_project.path, goal)
    return plan_goal(goal, ao_project.id, context)


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Development goal to decompose."),
    project: str = typer.Option(..., "--project", "-p", help="AO project ID/name/path."),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Turn one natural-language goal into a validated Bebop task graph."""
    goal_plan = _create_plan(goal, project)
    rendered = goal_plan.model_dump_json(indent=2)

    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(str(output))
    else:
        typer.echo(rendered)


@app.command()
def goal(
    goal: str = typer.Argument(..., help="Development goal to plan and execute."),
    project: str = typer.Option(..., "--project", "-p", help="AO project ID/name/path."),
) -> None:
    """Plan one goal, then execute its durable dependency graph."""
    goal_plan = _create_plan(goal, project)
    init_dbos()
    result = execute_goal(goal_plan.model_dump())
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
