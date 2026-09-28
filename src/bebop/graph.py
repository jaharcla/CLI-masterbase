from __future__ import annotations

from collections.abc import Mapping
from graphlib import TopologicalSorter

from bebop.models import GoalPlan


SUCCESS_STATES = {
    "verified",
    "verified_after_repair",
    "verified_after_escalation",
}


def build_sorter(plan: GoalPlan) -> TopologicalSorter:
    sorter = TopologicalSorter(
        {
            task.id: set(task.dependencies)
            for task in plan.tasks
        }
    )
    sorter.prepare()
    return sorter


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
