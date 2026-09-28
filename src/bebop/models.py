from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, BaseModel, Field


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
    id: str
    title: str
    objective: str
    project: str = Field(validation_alias=AliasChoices("project", "project_id"))
    relevant_files: list[str] = Field(default_factory=list)
    known_decisions: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)


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
