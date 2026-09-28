from __future__ import annotations

from enum import StrEnum
from graphlib import CycleError, TopologicalSorter
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, model_validator


class WorkClass(StrEnum):
    MECHANICAL = "mechanical"
    ROUTINE = "routine"
    ENGINEERING = "engineering"
    REASONING = "reasoning"
    CRITICAL = "critical"


class Dimension(BaseModel):
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    basis: list[str] = Field(default_factory=list)


class Classification(BaseModel):
    work_class: WorkClass
    reasoning: Dimension
    ambiguity: Dimension
    blast_radius: Dimension
    novelty: Dimension
    context_requirement: Dimension
    verifiability: Dimension
    security: Dimension
    reversibility: Dimension
    parallelizability: Dimension


class TaskCapsule(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    title: str
    objective: str
    project: str = Field(validation_alias=AliasChoices("project", "project_id"))
    run_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    known_decisions: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)


class GoalPlan(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    goal: str
    project: str
    tasks: list[TaskCapsule]

    @model_validator(mode="after")
    def validate_graph(self) -> "GoalPlan":
        if not self.tasks:
            raise ValueError("Goal plan must contain at least one task")

        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Task IDs must be unique")

        known = set(ids)
        for task in self.tasks:
            if task.project != self.project:
                raise ValueError(
                    f"Task {task.id} uses project {task.project!r}; "
                    f"goal project is {self.project!r}"
                )
            if task.id in task.dependencies:
                raise ValueError(f"Task {task.id} cannot depend on itself")
            if len(task.dependencies) != len(set(task.dependencies)):
                raise ValueError(f"Task {task.id} has duplicate dependencies")
            missing = set(task.dependencies) - known
            if missing:
                raise ValueError(
                    f"Task {task.id} has unknown dependencies: {sorted(missing)}"
                )

        graph = {
            task.id: set(task.dependencies)
            for task in self.tasks
        }
        try:
            TopologicalSorter(graph).prepare()
        except CycleError as exc:
            raise ValueError("Goal task graph contains a dependency cycle") from exc

        return self


class PlannedTask(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    title: str
    objective: str
    dependencies: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)


class PlanDraft(BaseModel):
    tasks: list[PlannedTask]

    @model_validator(mode="after")
    def validate_graph(self) -> "PlanDraft":
        if not self.tasks:
            raise ValueError("Plan must contain at least one task")

        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Planned task IDs must be unique")

        known = set(ids)
        for task in self.tasks:
            if task.id in task.dependencies:
                raise ValueError(f"Task {task.id} cannot depend on itself")
            missing = set(task.dependencies) - known
            if missing:
                raise ValueError(
                    f"Task {task.id} has unknown dependencies: {sorted(missing)}"
                )

        try:
            TopologicalSorter(
                {task.id: set(task.dependencies) for task in self.tasks}
            ).prepare()
        except CycleError as exc:
            raise ValueError("Planned task graph contains a dependency cycle") from exc

        return self


class RouteTarget(BaseModel):
    harness: str
    provider: str | None = None
    model: str | None = None
    effort: str | None = None
    mode: str = "chat"
    approval_mode: str = "default"
    reason: str


class AOProject(BaseModel):
    id: str
    name: str
    path: str = ""
    kind: str = ""
    folder_missing: bool = False


class WorkerSession(BaseModel):
    session_id: str
    project_id: str
    route: RouteTarget
    raw: dict[str, Any] = Field(default_factory=dict)


class AgentSwitch(BaseModel):
    id: str
    session_id: str = Field(validation_alias=AliasChoices("session_id", "sessionId"))
    from_harness: str = Field(
        default="",
        validation_alias=AliasChoices("from_harness", "fromHarness"),
    )
    target_harness: str = Field(
        default="",
        validation_alias=AliasChoices("target_harness", "targetHarness"),
    )
    target_start_mode: str = Field(
        default="",
        validation_alias=AliasChoices("target_start_mode", "targetStartMode"),
    )
    state: str
    agent_handoff_status: str = Field(
        default="",
        validation_alias=AliasChoices("agent_handoff_status", "agentHandoffStatus"),
    )
    semantic_handoff_included: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "semantic_handoff_included",
            "semanticHandoffIncluded",
        ),
    )
    error_code: str = Field(
        default="",
        validation_alias=AliasChoices("error_code", "errorCode"),
    )
    raw: dict[str, Any] = Field(default_factory=dict)


class SessionObservation(BaseModel):
    session_id: str
    status: str = ""
    activity_state: str = ""
    provision_state: str = ""
    is_terminated: bool = False
    changed_paths: list[str] = Field(default_factory=list)
    raw_session: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    command: str
    exit_code: int | None = None
    passed: bool
    output: str = ""
    duration_seconds: float = 0.0


class VerificationResult(BaseModel):
    passed: bool
    evidence: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    protected_path_changes: list[str] = Field(default_factory=list)
    out_of_scope_changes: list[str] = Field(default_factory=list)
    acceptance_pending: bool = False
    command_results: list[CommandResult] = Field(default_factory=list)


class TaskOutcome(BaseModel):
    state: str
    classification: Classification
    route: RouteTarget
    session: WorkerSession
    observation: SessionObservation
    verification: VerificationResult
    repair_attempts: int = 0
    escalation_attempts: int = 0
    escalated_route: RouteTarget | None = None
    agent_switch: AgentSwitch | None = None
    inherited_commits: list[str] = Field(default_factory=list)
    commit_sha: str | None = None


class GoalOutcome(BaseModel):
    state: str
    goal_id: str
    goal: str
    waves: list[list[str]] = Field(default_factory=list)
    task_outcomes: dict[str, TaskOutcome] = Field(default_factory=dict)
    blocked_tasks: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    integration_session: WorkerSession | None = None
    integration_commit_sha: str | None = None
    integration_verification: VerificationResult | None = None
