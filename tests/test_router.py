from bebop.classifier import classify
from bebop.models import TaskCapsule
from bebop.router import route


def test_security_task_routes_to_codex():
    task = TaskCapsule(
        id="T1",
        title="Change auth token validation",
        objective="Refactor authentication token validation",
        project_id="demo",
        relevant_files=["src/auth/token.py"],
        acceptance_commands=["pytest tests/auth"],
    )

    result = route(classify(task))

    assert result.harness == "codex"
    assert result.effort == "high"
