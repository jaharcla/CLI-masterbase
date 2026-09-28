from bebop.models import Task, TaskStatus
from bebop.state import StateStore


def test_task_round_trip(tmp_path):
    store = StateStore(tmp_path / "state.db")
    task = Task(
        id="T001",
        title="Inspect repository",
        dependencies=[],
        allowed_paths=["src/**"],
    )

    store.save_task(task)
    loaded = store.get_task("T001")

    assert loaded == task

    store.update_status("T001", TaskStatus.RUNNING)
    assert store.get_task("T001").status == TaskStatus.RUNNING

    store.close()
