from __future__ import annotations

from dbos import DBOS

from bebop.adapters.ao import AOClient
from bebop.classifier import classify
from bebop.models import Classification, RouteTarget, TaskCapsule, WorkerSession
from bebop.router import route


@DBOS.step()
def classify_step(task_payload: dict) -> dict:
    task = TaskCapsule.model_validate(task_payload)
    return classify(task).model_dump()


@DBOS.step()
def route_step(classification_payload: dict) -> dict:
    classification = Classification.model_validate(classification_payload)
    return route(classification).model_dump()


@DBOS.step()
def spawn_step(task_payload: dict, route_payload: dict) -> dict:
    task = TaskCapsule.model_validate(task_payload)
    target = RouteTarget.model_validate(route_payload)
    client = AOClient()
    try:
        return client.spawn(task, target).model_dump()
    finally:
        client.close()


@DBOS.workflow()
def execute_task(task_payload: dict) -> dict:
    """Durable handoff from Bebop intelligence to AO execution infrastructure."""
    classification = classify_step(task_payload)
    target = route_step(classification)
    session = spawn_step(task_payload, target)
    return {
        "classification": classification,
        "route": target,
        "session": WorkerSession.model_validate(session).model_dump(),
    }
