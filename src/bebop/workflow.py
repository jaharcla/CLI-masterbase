from __future__ import annotations

import hashlib

from dbos import DBOS

from bebop.adapters.ao import AOClient
from bebop.adapters.ao_terminal import AOTerminalVerifier
from bebop.classifier import classify
from bebop.models import (
    AOProject,
    AgentSwitch,
    CommandResult,
    RouteTarget,
    SessionObservation,
    TaskCapsule,
    TaskOutcome,
    VerificationResult,
    WorkerSession,
)
from bebop.router import escalation_route, route
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


@DBOS.step()
def switch_agent_step(
    session_id: str,
    route_payload: dict,
    idempotency_key: str,
) -> dict:
    client = AOClient()
    try:
        target = RouteTarget.model_validate(route_payload)
        return client.switch_agent(
            session_id,
            target,
            idempotency_key=idempotency_key,
        ).model_dump()
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


def _escalation_message(
    verification: VerificationResult,
    initial_route: RouteTarget,
) -> str:
    return (
        "Bebop escalated this existing AO session after the previous worker "
        "failed objective verification and one repair attempt. Preserve the "
        "current worktree, diagnose the underlying cause, and repair it. Do not "
        "weaken protected tests or acceptance criteria.\n\n"
        f"Previous route: {initial_route.harness}"
        + (f"/{initial_route.provider}" if initial_route.provider else "")
        + "\n\n"
        + _feedback_message(verification)
    )


def _escalation_idempotency_key(
    task: TaskCapsule,
    target: RouteTarget,
    attempt: int,
) -> str:
    material = (
        f"{task.id}|{attempt}|{target.harness}|{target.model or ''}"
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:32]
    return f"bebop-{task.id[:48]}-esc-{attempt}-{digest}"[:128]


def _run_verification(
    task: TaskCapsule,
    session_id: str,
    observation: SessionObservation,
) -> VerificationResult:
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
    """Route, execute, verify, repair cheaply, then escalate in-place when needed."""
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
    escalation_attempts = 0
    escalated_route: RouteTarget | None = None
    agent_switch: AgentSwitch | None = None

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
            if verification.passed:
                state = "verified_after_repair"
            else:
                escalated_route = escalation_route(target, classification)
                if escalated_route is None:
                    state = "strong_worker_failed"
                elif observation.activity_state not in {"idle", "waiting_input"}:
                    state = "escalation_unavailable_source_not_idle"
                else:
                    escalation_attempts = 1
                    agent_switch = AgentSwitch.model_validate(
                        switch_agent_step(
                            session.session_id,
                            escalated_route.model_dump(),
                            _escalation_idempotency_key(
                                task,
                                escalated_route,
                                escalation_attempts,
                            ),
                        )
                    )

                    if agent_switch.state != "completed":
                        state = "escalation_switch_failed"
                    else:
                        # The AO session id and worktree remain the same. Wait for
                        # the replacement controller to settle before sending the
                        # concrete verification failure that triggered escalation.
                        observation = SessionObservation.model_validate(
                            observe_step(session.session_id)
                        )
                        if observation.activity_state == "blocked":
                            state = "blocked_human_decision_required"
                            verification = inspect_workspace(
                                task,
                                observation.changed_paths,
                            )
                        else:
                            before_activity_at = _activity_timestamp(observation)
                            send_feedback_step(
                                session.session_id,
                                _escalation_message(verification, target),
                            )
                            observation = SessionObservation.model_validate(
                                observe_step(
                                    session.session_id,
                                    before_activity_at,
                                    True,
                                )
                            )

                            if observation.activity_state == "blocked":
                                state = "blocked_human_decision_required"
                                verification = inspect_workspace(
                                    task,
                                    observation.changed_paths,
                                )
                            else:
                                verification = _run_verification(
                                    task,
                                    session.session_id,
                                    observation,
                                )
                                state = (
                                    "verified_after_escalation"
                                    if verification.passed
                                    else "escalated_worker_failed"
                                )
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
        escalation_attempts=escalation_attempts,
        escalated_route=escalated_route,
        agent_switch=agent_switch,
    ).model_dump()
