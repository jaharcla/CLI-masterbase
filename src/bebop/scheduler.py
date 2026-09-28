from __future__ import annotations

from bebop.dag import TaskDag
from bebop.models import Task, TaskStatus
from bebop.state import StateStore


class Scheduler:
    """Deterministic MVP scheduler. Agent execution is intentionally separate."""

    def __init__(self, state: StateStore):
        self.state = state

    def add_tasks(self, tasks: list[Task]) -> None:
        TaskDag(tasks)
        for task in tasks:
            self.state.save_task(task)

    def refresh_ready(self) -> list[Task]:
        tasks = self.state.list_tasks()
        dag = TaskDag(tasks)
        ready = dag.ready_tasks()
        for task in ready:
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.READY
                self.state.save_task(task)
        return ready

    def mark_running(self, task_id: str) -> Task:
        return self.state.update_status(task_id, TaskStatus.RUNNING)

    def mark_passed(self, task_id: str) -> Task:
        return self.state.update_status(task_id, TaskStatus.PASSED)

    def mark_failed(self, task_id: str) -> Task:
        return self.state.update_status(task_id, TaskStatus.FAILED)
