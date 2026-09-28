from bebop.classifier import classify
from bebop.models import Classification, Dimension, RouteTarget, TaskCapsule, WorkClass
from bebop.router import antigravity_route, escalation_route, route


def test_security_task_routes_to_codex(monkeypatch):
    monkeypatch.delenv("BEBOP_HIGH_CAPABILITY_HARNESS", raising=False)
    task = TaskCapsule(
        id="T1",
        title="Change auth token validation",
        objective="Refactor authentication token validation",
        project="demo",
        relevant_files=["src/auth/token.py"],
        acceptance_commands=["pytest tests/auth"],
    )

    result = route(classify(task))

    assert result.harness == "codex"
    assert result.effort == "high"


def test_high_capability_route_can_select_antigravity(monkeypatch):
    monkeypatch.setenv("BEBOP_HIGH_CAPABILITY_HARNESS", "agy")

    result = route(_classification(WorkClass.REASONING))

    assert result.harness == "agy"
    assert result.effort == "medium"


def test_antigravity_route_helper_targets_ao_agy():
    result = antigravity_route()

    assert result.harness == "agy"
    assert result.provider is None


def test_routine_task_routes_to_opencode_ollama():
    task = TaskCapsule(
        id="T2",
        title="Implement parser",
        objective="Implement parser",
        project="demo",
        relevant_files=["src/parser.py"],
        acceptance_commands=["pytest tests/test_parser.py"],
    )

    result = route(classify(task))

    assert result.harness == "opencode"
    assert result.provider == "ollama"


def _classification(kind: WorkClass) -> Classification:
    dim = Dimension(value="medium", confidence=0.8, basis=["test"])
    return Classification(
        work_class=kind,
        reasoning=dim,
        ambiguity=dim,
        blast_radius=dim,
        novelty=dim,
        context_requirement=dim,
        verifiability=dim,
        security=dim,
        reversibility=dim,
        parallelizability=dim,
    )


def test_opencode_escalates_to_codex():
    result = escalation_route(
        RouteTarget(harness="opencode", provider="ollama", reason="initial"),
        _classification(WorkClass.ROUTINE),
    )

    assert result is not None
    assert result.harness == "codex"
    assert result.effort == "medium"


def test_codex_has_no_stronger_route_yet():
    result = escalation_route(
        RouteTarget(harness="codex", effort="high", reason="initial"),
        _classification(WorkClass.CRITICAL),
    )

    assert result is None
