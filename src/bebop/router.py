from __future__ import annotations

from bebop.models import Classification, RouteTarget, WorkClass


def route(classification: Classification) -> RouteTarget:
    """Explicit first-pass policy. Provider choice is separate from concrete model IDs."""
    kind = classification.work_class

    if kind in {WorkClass.MECHANICAL, WorkClass.ROUTINE}:
        return RouteTarget(
            harness="opencode",
            provider="ollama",
            reason="cheap, highly verifiable work gets a local/unmetered first attempt",
        )

    if kind == WorkClass.ENGINEERING:
        return RouteTarget(
            harness="opencode",
            provider="groq",
            reason="engineering work defaults to fast cloud inference",
        )

    return RouteTarget(
        harness="codex",
        effort="high" if kind == WorkClass.CRITICAL else "medium",
        reason="reasoning/critical work is protected for the strongest worker",
    )
