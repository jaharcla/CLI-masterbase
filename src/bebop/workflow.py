from __future__ import annotations

from dbos import DBOS

from bebop.adapters.ao import AOClient
from bebop.classifier import classify
from bebop.models import (
    AOProject,
    RouteTarget,
    SessionObservation,
    TaskCapsule,
    TaskOutcome,
    WorkerSession,
)
from bebop.router import route
from bebop.verification import inspect_workspace


@DBOS.step()
def resolve_project_step(selector: str) -> dict:
    client = AOClient()
    try:
        return client.resolve_project(selector).model_dump()
    finally:
        client.close()


@DBOS.step()
def spawn_step(task_payload: dict, route_payload: dict, project_id: str) -> dict:
    task = TaskCapsule.model_validate(task_payload)
    target = RouteTarget.model_validate(route_payload)
    client = AOClient()
    try:
        return client.spawn(task, target, project_id).model_dump()
    finally:
        client.close()


@DBOS.step()
def observe_step(session_id: str) -> dict:
    client = AOClient()
    try:
        return client.observe_until_settled(session_id).model_dump()
    finally:
        client.close()


@DBOS.step()
def send_feedback_step(session_id: str, message: str) -> None:
    client = AOClient()
    try:
        client.send(session_id, message)
    finally:
        client.close()


@DBOS.workflow()
def execute_task(task_payload: dict) -> dict:
    """Route one task through reused durable/execution infrastructure."""
    task = TaskCapsule.model_validate(task_payload)

    # Deterministic Bebop intelligence stays inside the workflow. Only external
    # I/O becomes DBOS steps.
    classification = classify(task)
    target = route(classification)

    project = AOProject.model_validate(resolve_project_step(task.project))
    session = WorkerSession.model_validate(
        spawn_step(task.model_dump(), target.model_dump(), project.id)
    )
    observation = SessionObservation.model_validate(observe_step(session.session_id))
    verification = inspect_workspace(task, observation.changed_paths)

    if observation.activity_state == "blocked":
        state = "blocked_human_decision_required"
    elif verification.protected_path_changes:
        state = "policy_failed"
        if observation.activity_state in {"idle", "waiting_input"}:
            send_feedback_step(
                session.session_id,
                "Bebop policy check failed: protected verification artifacts were changed: "
                + ", ".join(verification.protected_path_changes)
                + ". Revert those protected changes and fix the implementation without "
                "weakening the acceptance criteria.",
            )
            state = "policy_failed_feedback_sent"
    elif verification.acceptance_pending:
        state = "awaiting_objective_verification"
    else:
        state = "policy_passed"

    return TaskOutcome(
        state=state,
        classification=classification,
        route=target,
        session=session,
        observation=observation,
        verification=verification,
    ).model_dump()
