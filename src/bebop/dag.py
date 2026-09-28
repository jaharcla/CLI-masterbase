from __future__ import annotations

from collections import defaultdict, deque

from bebop.models import Task, TaskStatus


class InvalidDag(ValueError):
    pass


class TaskDag:
    def __init__(self, tasks: list[Task]):
        self.tasks = {task.id: task for task in tasks}
        if len(self.tasks) != len(tasks):
            raise InvalidDag("Task IDs must be unique")
        self._validate_dependencies()
        self._validate_acyclic()

    def _validate_dependencies(self) -> None:
        known = set(self.tasks)
        for task in self.tasks.values():
            missing = set(task.dependencies) - known
            if missing:
                raise InvalidDag(
                    f"{task.id} depends on unknown task(s): {sorted(missing)}"
                )

    def _validate_acyclic(self) -> None:
        indegree = {task_id: 0 for task_id in self.tasks}
        edges: dict[str, list[str]] = defaultdict(list)
        for task in self.tasks.values():
            for dependency in task.dependencies:
                edges[dependency].append(task.id)
                indegree[task.id] += 1

        queue = deque(task_id for task_id, degree in indegree.items() if degree == 0)
        seen = 0
        while queue:
            current = queue.popleft()
            seen += 1
            for child in edges[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        if seen != len(self.tasks):
            raise InvalidDag("Task graph contains a cycle")

    def ready_tasks(self) -> list[Task]:
        ready: list[Task] = []
        for task in self.tasks.values():
            if task.status not in {TaskStatus.PENDING, TaskStatus.READY}:
                continue
            dependencies = [self.tasks[dep] for dep in task.dependencies]
            if all(
                dep.status in {TaskStatus.PASSED, TaskStatus.INTEGRATED}
                for dep in dependencies
            ):
                ready.append(task)
        return sorted(ready, key=lambda task: task.id)
