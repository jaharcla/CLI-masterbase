from bebop.classifier import classify
from bebop.models import TaskCapsule
from bebop.router import route


def test_security_task_routes_to_codex():
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
