import pytest
from pydantic import ValidationError

from bebop.graph import build_sorter, dependency_lineage
from bebop.models import GoalPlan, TaskCapsule


def _task(task_id, dependencies=None):
    return TaskCapsule(
        id=task_id,
        title=task_id,
        objective=task_id,
        project="demo",
        dependencies=dependencies or [],
    )


def test_graphlib_exposes_parallel_ready_wave():
    plan = GoalPlan(
        id="run-1",
        goal="demo",
        project="demo",
        tasks=[
            _task("T1"),
            _task("T2"),
            _task("T3", ["T1", "T2"]),
        ],
    )

    sorter = build_sorter(plan)
    assert set(sorter.get_ready()) == {"T1", "T2"}

    sorter.done("T1", "T2")
    assert tuple(sorter.get_ready()) == ("T3",)


def test_goal_plan_rejects_cycle():
    with pytest.raises(ValidationError):
        GoalPlan(
            id="run-1",
            goal="demo",
            project="demo",
            tasks=[
                _task("T1", ["T2"]),
                _task("T2", ["T1"]),
            ],
        )


def test_dependency_lineage_carries_transitive_commits():
    plan = GoalPlan(
        id="run-1",
        goal="demo",
        project="demo",
        tasks=[
            _task("T1"),
            _task("T2", ["T1"]),
            _task("T3", ["T2"]),
        ],
    )

    lineages = {
        "T1": ["a" * 40],
        "T2": ["a" * 40, "b" * 40],
    }

    assert dependency_lineage("T3", plan, lineages) == [
        "a" * 40,
        "b" * 40,
    ]
