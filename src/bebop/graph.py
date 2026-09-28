from __future__ import annotations

from collections.abc import Mapping

from bebop.models import GoalPlan, TaskOutcome


SUCCESS_STATES = {
    "verified",
    "verified_after_repair",
    "verified_after_escalation",
}


def ready_tasks(
    plan: GoalPlan,
    completed: Mapping[str, TaskOutcome],
    pending_ids: set[str],
) -> list[str]:
    ready: list[str] = []
    for task in plan.tasks:
        if task.id not in pending_ids:
            continue
        if all(
            dependency in completed
            and completed[dependency].state in SUCCESS_STATES
            for dependency in task.dependencies
        ):
            ready.append(task.id)
    return sorted(ready)


def blocked_tasks(
    plan: GoalPlan,
    completed: Mapping[str, TaskOutcome],
    pending_ids: set[str],
) -> list[str]:
    blocked: list[str] = []
    for task in plan.tasks:
        if task.id not in pending_ids:
            continue
        if any(
            dependency in completed
            and completed[dependency].state not in SUCCESS_STATES
            for dependency in task.dependencies
        ):
            blocked.append(task.id)
    return sorted(blocked)


def dependency_lineage(
    task_id: str,
    plan: GoalPlan,
    lineages: Mapping[str, list[str]],
) -> list[str]:
    tasks = {task.id: task for task in plan.tasks}
    task = tasks[task_id]
    commits: list[str] = []
    seen: set[str] = set()

    for dependency in task.dependencies:
        for commit in lineages.get(dependency, []):
            if commit and commit not in seen:
                commits.append(commit)
                seen.add(commit)

    return commits
