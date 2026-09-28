from __future__ import annotations

from bebop.models import Classification, Dimension, TaskCapsule, WorkClass


_SECURITY_MARKERS = ("auth", "permission", "secret", "crypto", "token", "payment")
_HIGH_RISK_MARKERS = ("migration", "schema", "concurrency", "lock", "persistence")


def classify(task: TaskCapsule) -> Classification:
    """Cheap deterministic baseline. An LLM classifier can enrich this later."""
    haystack = " ".join(
        [task.title, task.objective, *task.relevant_files]
    ).lower()

    security = any(marker in haystack for marker in _SECURITY_MARKERS)
    high_risk = any(marker in haystack for marker in _HIGH_RISK_MARKERS)
    verifiable = bool(task.acceptance_commands)

    if security:
        work_class = WorkClass.CRITICAL
    elif high_risk:
        work_class = WorkClass.REASONING
    elif len(task.relevant_files) > 5:
        work_class = WorkClass.ENGINEERING
    elif len(task.relevant_files) <= 1 and verifiable:
        work_class = WorkClass.ROUTINE
    else:
        work_class = WorkClass.ENGINEERING

    def d(value: str, confidence: float, *basis: str) -> Dimension:
        return Dimension(value=value, confidence=confidence, basis=list(basis))

    return Classification(
        work_class=work_class,
        reasoning=d("high" if high_risk or security else "medium", 0.65, "baseline heuristic"),
        ambiguity=d("medium", 0.45, "requires planner enrichment"),
        blast_radius=d("high" if len(task.relevant_files) > 5 else "medium", 0.6, "file-count proxy"),
        novelty=d("medium", 0.4, "unknown until repo analysis"),
        context_requirement=d("high" if len(task.relevant_files) > 5 else "medium", 0.6, "relevant file count"),
        verifiability=d("high" if verifiable else "low", 0.9, "acceptance commands present" if verifiable else "no acceptance commands"),
        security=d("high" if security else "low", 0.85, "security path/text markers"),
        reversibility=d("high", 0.7, "AO isolates work in git worktrees"),
        parallelizability=d("medium", 0.5, "dependency graph not yet supplied"),
    )
