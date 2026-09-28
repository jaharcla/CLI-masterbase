import pytest

from bebop.dag import InvalidDag, TaskDag
from bebop.models import Task, TaskStatus


def test_ready_tasks_respect_dependencies():
    first = Task(id="T001", title="first", status=TaskStatus.PASSED)
    second = Task(id="T002", title="second", dependencies=["T001"])
    third = Task(id="T003", title="third", dependencies=["T002"])

    dag = TaskDag([first, second, third])

    assert [task.id for task in dag.ready_tasks()] == ["T002"]


def test_cycle_is_rejected():
    tasks = [
        Task(id="T001", title="one", dependencies=["T002"]),
        Task(id="T002", title="two", dependencies=["T001"]),
    ]

    with pytest.raises(InvalidDag):
        TaskDag(tasks)
