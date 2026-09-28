from bebop.models import Task, TaskStatus
from bebop.scheduler import Scheduler
from bebop.state import StateStore


def test_scheduler_unlocks_dependency_chain(tmp_path):
    store = StateStore(tmp_path / "state.db")
    scheduler = Scheduler(store)

    scheduler.add_tasks(
        [
            Task(id="T001", title="inspect"),
            Task(id="T002", title="implement", dependencies=["T001"]),
        ]
    )

    ready = scheduler.refresh_ready()
    assert [task.id for task in ready] == ["T001"]
    assert store.get_task("T001").status == TaskStatus.READY

    scheduler.mark_passed("T001")

    ready = scheduler.refresh_ready()
    assert [task.id for task in ready] == ["T002"]
    assert store.get_task("T002").status == TaskStatus.READY

    store.close()
