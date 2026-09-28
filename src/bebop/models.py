from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field


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
    project_id: str
    relevant_files: list[str] = Field(default_factory=list)
    known_decisions: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)


class RouteTarget(BaseModel):
    harness: str
    model: str | None = None
    effort: str | None = None
    mode: str = "chat"
    approval_mode: str = "default"
    reason: str


class WorkerSession(BaseModel):
    session_id: str
    project_id: str
    route: RouteTarget
    raw: dict = Field(default_factory=dict)


class VerificationResult(BaseModel):
    passed: bool
    evidence: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    protected_path_changes: list[str] = Field(default_factory=list)
