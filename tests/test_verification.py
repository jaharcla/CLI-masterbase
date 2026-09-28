from bebop.models import TaskCapsule
from bebop.verification import check_protected_paths


def test_protected_test_change_fails_policy():
    task = TaskCapsule(
        id="T1",
        title="Implement parser",
        objective="Implement parser",
        project_id="demo",
        protected_paths=["tests/**"],
    )

    result = check_protected_paths(task, ["src/parser.py", "tests/test_parser.py"])

    assert result.passed is False
    assert result.protected_path_changes == ["tests/test_parser.py"]
