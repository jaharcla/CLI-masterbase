from __future__ import annotations

from bebop.models import Classification, RouteTarget, WorkClass


def route(classification: Classification) -> RouteTarget:
    """Explicit first-pass policy. Keep routing transparent and testable."""
    kind = classification.work_class

    if kind == WorkClass.MECHANICAL:
        return RouteTarget(
            harness="opencode",
            model="ollama",
            reason="mechanical work defaults to local/unmetered inference",
        )

    if kind == WorkClass.ROUTINE:
        return RouteTarget(
            harness="opencode",
            model="ollama",
            reason="routine + verifiable work gets a cheap first attempt",
        )

    if kind == WorkClass.ENGINEERING:
        return RouteTarget(
            harness="opencode",
            model="groq",
            reason="engineering work defaults to fast cloud inference",
        )

    return RouteTarget(
        harness="codex",
        effort="high" if kind == WorkClass.CRITICAL else "medium",
        reason="reasoning/critical work is protected for the strongest worker",
    )
