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


def escalation_route(
    current: RouteTarget,
    classification: Classification,
) -> RouteTarget | None:
    """Choose the next materially stronger AO-native route.

    AO's durable in-place agent switching currently targets provider harnesses,
    not a different model behind the same OpenCode harness. Therefore a failed
    OpenCode task escalates directly to Codex while retaining the same AO
    session/worktree. A Codex task has no stronger configured route yet.
    """
    if current.harness == "codex":
        return None

    effort = (
        "high"
        if classification.work_class in {WorkClass.REASONING, WorkClass.CRITICAL}
        else "medium"
    )
    return RouteTarget(
        harness="codex",
        effort=effort,
        reason=(
            "objective verification still failed after a same-worker repair; "
            "switch the existing AO session to Codex for stronger diagnosis and repair"
        ),
    )
