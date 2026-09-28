from __future__ import annotations

from dbos import DBOS

from bebop.adapters.ao import AOClient
from bebop.adapters.ao_terminal import AOTerminalVerifier
from bebop.classifier import classify
from bebop.models import (
    AOProject,
    CommandResult,
    RouteTarget,
    SessionObservation,
    TaskCapsule,
    TaskOutcome,
    VerificationResult,
    WorkerSession,
)
from bebop.router import route
from bebop.verification import apply_command_results, inspect_workspace


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
def observe_step(
    session_id: str,
    after_activity_at: str | None = None,
    require_progress: bool = False,
) -> dict:
    client = AOClient()
    try:
        return client.observe_until_settled(
            session_id,
            after_activity_at=after_activity_at,
            require_progress=require_progress,
        ).model_dump()
    finally:
        client.close()


@DBOS.step()
def send_feedback_step(session_id: str, message: str) -> None:
    client = AOClient()
    try:
        client.send(session_id, message)
    finally:
        client.close()


@DBOS.step()
def verify_commands_step(session_id: str, commands: list[str]) -> list[dict]:
    client = AOClient()
    try:
        verifier = AOTerminalVerifier(client)
        return [result.model_dump() for result in verifier.run_commands(session_id, commands)]
    finally:
        client.close()


def _activity_timestamp(observation: SessionObservation) -> str | None:
    activity = observation.raw_session.get("activity") or {}
    value = str(activity.get("lastActivityAt", ""))
    return value or None


def _feedback_message(verification: VerificationResult) -> str:
    lines = [
        "Bebop verification failed. Fix the implementation without weakening tests or acceptance criteria."
    ]
    if verification.protected_path_changes:
        lines.append(
            "Protected files changed: " + ", ".join(verification.protected_path_changes)
        )
    for result in verification.command_results:
        if result.passed:
            continue
        output = result.output[-6000:]
        lines.append(
            f"Failed command: {result.command}\n"
            f"Exit code: {result.exit_code}\n"
            f"Output tail:\n{output}"
        )
    return "\n\n".join(lines)


def _run_verification(task: TaskCapsule, session_id: str, observation: SessionObservation) -> VerificationResult:
    policy = inspect_workspace(task, observation.changed_paths)
    if policy.protected_path_changes or not task.acceptance_commands:
        return policy

    results = [
        CommandResult.model_validate(item)
        for item in verify_commands_step(session_id, task.acceptance_commands)
    ]
    return apply_command_results(policy, task.acceptance_commands, results)


@DBOS.workflow()
def execute_task(task_payload: dict) -> dict:
    """Route, execute, objectively verify, and repair one bounded coding task."""
    task = TaskCapsule.model_validate(task_payload)
    classification = classify(task)
    target = route(classification)

    project = AOProject.model_validate(resolve_project_step(task.project))
    session = WorkerSession.model_validate(
        spawn_step(task.model_dump(), target.model_dump(), project.id)
    )

    observation = SessionObservation.model_validate(observe_step(session.session_id))
    verification = _run_verification(task, session.session_id, observation)
    repair_attempts = 0

    if observation.activity_state == "blocked":
        state = "blocked_human_decision_required"
    elif verification.passed:
        state = "verified"
    elif observation.activity_state in {"idle", "waiting_input"}:
        before_activity_at = _activity_timestamp(observation)
        send_feedback_step(session.session_id, _feedback_message(verification))
        repair_attempts = 1

        observation = SessionObservation.model_validate(
            observe_step(
                session.session_id,
                before_activity_at,
                True,
            )
        )

        if observation.activity_state == "blocked":
            state = "blocked_human_decision_required"
            verification = inspect_workspace(task, observation.changed_paths)
        else:
            verification = _run_verification(task, session.session_id, observation)
            state = "verified_after_repair" if verification.passed else "needs_escalation"
    else:
        state = "needs_escalation"

    return TaskOutcome(
        state=state,
        classification=classification,
        route=target,
        session=session,
        observation=observation,
        verification=verification,
        repair_attempts=repair_attempts,
    ).model_dump()
