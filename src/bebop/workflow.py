from __future__ import annotations

import hashlib

from dbos import DBOS

from bebop.adapters.ao import AOClient, AOError, render_task_capsule
from bebop.adapters.ao_terminal import AOTerminalVerifier
from bebop.adapters.git_handoff import GitHandoff
from bebop.classifier import classify
from bebop.graph import SUCCESS_STATES, build_sorter, dependency_lineage, ordered_verified_commits
from bebop.models import (
    AOProject,
    AgentSwitch,
    CommandResult,
    GoalOutcome,
    GoalPlan,
    RouteTarget,
    SessionObservation,
    TaskCapsule,
    TaskOutcome,
    VerificationResult,
    WorkerSession,
)
from bebop.router import escalation_route, route
from bebop.runtime import TASK_QUEUE
from bebop.verification import apply_command_results, inspect_workspace
from bebop.verifier_registry import discover_verification_commands


@DBOS.step()
def resolve_project_step(selector: str) -> dict:
    client = AOClient()
    try:
        return client.resolve_project(selector).model_dump()
    finally:
        client.close()


@DBOS.step()
def spawn_step(
    task_payload: dict,
    route_payload: dict,
    project_id: str,
    deliver_prompt: bool = True,
) -> dict:
    task = TaskCapsule.model_validate(task_payload)
    target = RouteTarget.model_validate(route_payload)
    client = AOClient()
    try:
        return client.spawn(
            task,
            target,
            project_id,
            deliver_prompt=deliver_prompt,
        ).model_dump()
    finally:
        client.close()


@DBOS.step()
def observe_step(
    session_id: str,
    after_activity_at: str | None = None,
    require_progress: bool = False,
    ignored_commits: list[str] | None = None,
) -> dict:
    client = AOClient()
    try:
        return client.observe_until_settled(
            session_id,
            after_activity_at=after_activity_at,
            require_progress=require_progress,
            ignored_commits=set(ignored_commits or []),
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
def send_task_step(session_id: str, task_payload: dict) -> None:
    task = TaskCapsule.model_validate(task_payload)
    client = AOClient()
    try:
        client.send(session_id, render_task_capsule(task))
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
def discover_verification_step(session_id: str) -> list[str]:
    client = AOClient()
    try:
        return discover_verification_commands(client.workspace_paths(session_id))
    finally:
        client.close()


@DBOS.step()
def integrate_dependency_commits_step(
    session_id: str,
    commits: list[str],
) -> dict:
    client = AOClient()
    try:
        baseline_sha = GitHandoff(client).integrate_commits(session_id, commits)
        return {"ok": True, "baseline_sha": baseline_sha}
    except AOError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        client.close()


@DBOS.step()
def commit_verified_step(
    session_id: str,
    task_id: str,
    baseline_sha: str,
) -> dict:
    client = AOClient()
    try:
        commit_sha = GitHandoff(client).commit_verified_changes(
            session_id,
            task_id,
            baseline_sha,
        )
        return {"ok": True, "commit_sha": commit_sha}
    except AOError as exc:
        return {"ok": False, "error": str(exc), "commit_sha": None}
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
    if verification.out_of_scope_changes:
        lines.append(
            "Out-of-scope files changed: " + ", ".join(verification.out_of_scope_changes)
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
        f"{task.run_id or ''}|{task.id}|{attempt}|{target.harness}|{target.model or ''}"
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:32]
    return f"bebop-{task.id[:40]}-esc-{attempt}-{digest}"[:128]


def _run_verification(
    task: TaskCapsule,
    session_id: str,
    observation: SessionObservation,
) -> VerificationResult:
    policy = inspect_workspace(task, observation.changed_paths)
    if policy.protected_path_changes or policy.out_of_scope_changes:
        return policy

    commands = list(task.acceptance_commands)
    source = "explicit"
    if not commands:
        commands = discover_verification_step(session_id)
        source = "auto-discovered"

    if not commands:
        return VerificationResult(
            passed=False,
            evidence=[
                *policy.evidence,
                "no objective verification command could be discovered",
            ],
            failures=[
                *policy.failures,
                "objective verification unavailable",
            ],
            protected_path_changes=policy.protected_path_changes,
            out_of_scope_changes=policy.out_of_scope_changes,
            acceptance_pending=True,
        )

    results = [
        CommandResult.model_validate(item)
        for item in verify_commands_step(session_id, commands)
    ]
    verified = apply_command_results(policy, commands, results)
    verified.evidence.append(f"verification commands source: {source}")
    return verified


def _early_outcome(
    *,
    state: str,
    task: TaskCapsule,
    classification,
    target: RouteTarget,
    session: WorkerSession,
    observation: SessionObservation,
    failures: list[str],
    inherited_commits: list[str],
) -> dict:
    return TaskOutcome(
        state=state,
        classification=classification,
        route=target,
        session=session,
        observation=observation,
        verification=VerificationResult(
            passed=False,
            failures=failures,
            evidence=[],
        ),
        inherited_commits=inherited_commits,
    ).model_dump()


@DBOS.workflow()
def execute_task(
    task_payload: dict,
    inherited_commits: list[str] | None = None,
) -> dict:
    """Execute one bounded task, optionally inheriting verified dependency commits."""
    task = TaskCapsule.model_validate(task_payload)
    inherited = list(inherited_commits or [])
    graph_mode = inherited_commits is not None

    classification = classify(task)
    target = route(classification)

    project = AOProject.model_validate(resolve_project_step(task.project))
    session = WorkerSession.model_validate(
        spawn_step(
            task.model_dump(),
            target.model_dump(),
            project.id,
            not graph_mode,
        )
    )

    baseline_sha: str | None = None

    if graph_mode:
        # Let AO finish provisioning the idle session/worktree before importing
        # verified predecessor commits.
        observation = SessionObservation.model_validate(
            observe_step(session.session_id, ignored_commits=inherited)
        )
        if observation.activity_state == "blocked":
            return _early_outcome(
                state="blocked_human_decision_required",
                task=task,
                classification=classification,
                target=target,
                session=session,
                observation=observation,
                failures=["AO worker is waiting on a human decision before task start"],
                inherited_commits=inherited,
            )

        integration = integrate_dependency_commits_step(session.session_id, inherited)
        if not integration.get("ok"):
            return _early_outcome(
                state="dependency_integration_failed",
                task=task,
                classification=classification,
                target=target,
                session=session,
                observation=observation,
                failures=[str(integration.get("error", "dependency integration failed"))],
                inherited_commits=inherited,
            )

        baseline_sha = str(integration.get("baseline_sha") or "")
        if not baseline_sha:
            return _early_outcome(
                state="dependency_integration_failed",
                task=task,
                classification=classification,
                target=target,
                session=session,
                observation=observation,
                failures=["dependency integration did not produce a baseline SHA"],
                inherited_commits=inherited,
            )

        before_activity_at = _activity_timestamp(observation)
        send_task_step(session.session_id, task.model_dump())
        observation = SessionObservation.model_validate(
            observe_step(
                session.session_id,
                before_activity_at,
                True,
                inherited,
            )
        )
    else:
        observation = SessionObservation.model_validate(
            observe_step(session.session_id)
        )

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
                inherited,
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
                        observation = SessionObservation.model_validate(
                            observe_step(
                                session.session_id,
                                ignored_commits=inherited,
                            )
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
                                    inherited,
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

    commit_sha: str | None = None
    if graph_mode and state in SUCCESS_STATES:
        if baseline_sha is None:
            state = "verified_but_commit_failed"
            committed = {"ok": False, "error": "task baseline SHA missing"}
        else:
            committed = commit_verified_step(
                session.session_id,
                task.id,
                baseline_sha,
            )
        if not committed.get("ok"):
            state = "verified_but_commit_failed"
        else:
            commit_sha = committed.get("commit_sha")

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
        inherited_commits=inherited,
        commit_sha=commit_sha,
    ).model_dump()


@DBOS.workflow()
def execute_goal(plan_payload: dict) -> dict:
    """Execute a validated goal DAG and compose verified work in one AO workspace."""
    plan = GoalPlan.model_validate(plan_payload)
    task_by_id = {task.id: task for task in plan.tasks}
    sorter = build_sorter(plan)

    outcomes: dict[str, TaskOutcome] = {}
    lineages: dict[str, list[str]] = {}
    waves: list[list[str]] = []
    errors: dict[str, str] = {}

    while sorter.is_active():
        ready = sorted(sorter.get_ready())
        if not ready:
            break

        waves.append(ready)
        handles: list[tuple[str, list[str], object]] = []

        for task_id in ready:
            task = task_by_id[task_id].model_copy(update={"run_id": plan.id})
            inherited = dependency_lineage(task_id, plan, lineages)
            handle = DBOS.enqueue_workflow(
                TASK_QUEUE,
                execute_task,
                task.model_dump(),
                inherited,
            )
            handles.append((task_id, inherited, handle))

        for task_id, inherited, handle in handles:
            try:
                outcome = TaskOutcome.model_validate(handle.get_result())
            except Exception as exc:
                errors[task_id] = str(exc)
                continue

            outcomes[task_id] = outcome
            if outcome.state not in SUCCESS_STATES:
                continue

            lineage = list(inherited)
            if outcome.commit_sha and outcome.commit_sha not in lineage:
                lineage.append(outcome.commit_sha)
            lineages[task_id] = lineage
            sorter.done(task_id)

    executed_ids = set(outcomes) | set(errors)
    blocked = sorted(set(task_by_id) - executed_ids)
    non_success = [
        task_id
        for task_id, outcome in outcomes.items()
        if outcome.state not in SUCCESS_STATES
    ]

    integration_session: WorkerSession | None = None
    integration_commit_sha: str | None = None
    integration_verification: VerificationResult | None = None

    all_tasks_verified = (
        not blocked
        and not errors
        and not non_success
        and len(outcomes) == len(plan.tasks)
    )

    if all_tasks_verified:
        commits = ordered_verified_commits(waves, outcomes)
        if commits:
            integration_task = TaskCapsule(
                id="integration",
                title="Integrate verified goal",
                objective=plan.goal,
                project=plan.project,
                run_id=plan.id,
            )
            integration_target = RouteTarget(
                harness="opencode",
                reason="AO-owned goal integration workspace",
            )
            project = AOProject.model_validate(resolve_project_step(plan.project))
            integration_session = WorkerSession.model_validate(
                spawn_step(
                    integration_task.model_dump(),
                    integration_target.model_dump(),
                    project.id,
                    False,
                )
            )

            ready_observation = SessionObservation.model_validate(
                observe_step(integration_session.session_id)
            )
            if ready_observation.activity_state == "blocked":
                state = "blocked_human_decision_required"
            else:
                integrated = integrate_dependency_commits_step(
                    integration_session.session_id,
                    commits,
                )
                if not integrated.get("ok"):
                    state = "integration_failed"
                    errors["integration"] = str(
                        integrated.get("error", "goal integration failed")
                    )
                else:
                    integration_commit_sha = str(
                        integrated.get("baseline_sha") or ""
                    ) or None
                    commands = discover_verification_step(
                        integration_session.session_id
                    )
                    if not commands:
                        integration_verification = VerificationResult(
                            passed=False,
                            evidence=[
                                "verified task commits integrated in AO workspace",
                                "no repo-wide verification command discovered",
                            ],
                            failures=["objective goal-level verification unavailable"],
                            acceptance_pending=True,
                        )
                        state = "integration_unverified"
                    else:
                        command_results = [
                            CommandResult.model_validate(item)
                            for item in verify_commands_step(
                                integration_session.session_id,
                                commands,
                            )
                        ]
                        integration_verification = apply_command_results(
                            VerificationResult(
                                passed=False,
                                evidence=[
                                    "verified task commits integrated in AO workspace"
                                ],
                                acceptance_pending=True,
                            ),
                            commands,
                            command_results,
                        )
                        integration_verification.evidence.append(
                            "verification commands source: auto-discovered"
                        )
                        state = (
                            "verified"
                            if integration_verification.passed
                            else "integration_verification_failed"
                        )
        else:
            # A fully verified no-op goal is still complete.
            state = "verified"
    elif any(
        outcome.state == "blocked_human_decision_required"
        for outcome in outcomes.values()
    ):
        state = "blocked_human_decision_required"
    else:
        state = "partial_failure"

    return GoalOutcome(
        state=state,
        goal_id=plan.id,
        goal=plan.goal,
        waves=waves,
        task_outcomes=outcomes,
        blocked_tasks=blocked,
        errors=errors,
        integration_session=integration_session,
        integration_commit_sha=integration_commit_sha,
        integration_verification=integration_verification,
    ).model_dump()
