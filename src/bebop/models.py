from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    VERIFYING = "verifying"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    INTEGRATED = "integrated"
    CANCELLED = "cancelled"


class TaskClass(StrEnum):
    MECHANICAL = "mechanical"
    ROUTINE = "routine"
    ENGINEERING = "engineering"
    REASONING = "reasoning"
    CRITICAL = "critical"


class Task(BaseModel):
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    task_class: TaskClass | None = None
    dependencies: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)
    assigned_worker: str | None = None
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(BaseModel):
    status: str
    summary: str = ""
    files_changed: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    needs_escalation: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
