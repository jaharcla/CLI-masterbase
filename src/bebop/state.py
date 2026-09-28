from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bebop.models import Task, TaskStatus


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    PRIMARY KEY (task_id, depends_on)
);
"""


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def save_task(self, task: Task) -> None:
        payload = task.model_dump_json()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO tasks (id, payload, status)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    status=excluded.status
                """,
                (task.id, payload, task.status.value),
            )
            self.connection.execute(
                "DELETE FROM task_dependencies WHERE task_id = ?",
                (task.id,),
            )
            self.connection.executemany(
                "INSERT INTO task_dependencies (task_id, depends_on) VALUES (?, ?)",
                [(task.id, dep) for dep in task.dependencies],
            )

    def get_task(self, task_id: str) -> Task | None:
        row = self.connection.execute(
            "SELECT payload FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return Task.model_validate_json(row[0]) if row else None

    def list_tasks(self) -> list[Task]:
        rows = self.connection.execute(
            "SELECT payload FROM tasks ORDER BY id"
        ).fetchall()
        return [Task.model_validate_json(row[0]) for row in rows]

    def update_status(self, task_id: str, status: TaskStatus) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        task.status = status
        self.save_task(task)
        return task

    def dump(self) -> list[dict]:
        return [json.loads(task.model_dump_json()) for task in self.list_tasks()]
