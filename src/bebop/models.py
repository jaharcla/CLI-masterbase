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


class SessionObservation(BaseModel):
    session_id: str
    status: str = ""
    activity_state: str = ""
    provision_state: str = ""
    is_terminated: bool = False
    changed_paths: list[str] = Field(default_factory=list)
    raw_session: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    passed: bool
    evidence: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    protected_path_changes: list[str] = Field(default_factory=list)
    acceptance_pending: bool = False


class TaskOutcome(BaseModel):
    state: str
    classification: Classification
    route: RouteTarget
    session: WorkerSession
    observation: SessionObservation
    verification: VerificationResult
