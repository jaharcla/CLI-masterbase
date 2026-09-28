from bebop.models import TaskCapsule
from bebop.verification import check_protected_paths


def test_gitwildmatch_protected_change_fails_policy():
    task = TaskCapsule(
        id="T1",
        title="Implement parser",
        objective="Implement parser",
        project_id="demo",
        protected_paths=["tests/**/*.py", "!tests/fixtures/**"],
    )

    result = check_protected_paths(
        task,
        ["src/parser.py", "tests/test_parser.py", "tests/fixtures/sample.py"],
    )

    assert result.passed is False
    assert result.protected_path_changes == ["tests/test_parser.py"]


def test_allowed_paths_reject_out_of_scope_changes():
    task = TaskCapsule(
        id="T2",
        title="Implement parser",
        objective="Implement parser",
        project_id="demo",
        allowed_paths=["src/**"],
    )

    result = check_protected_paths(
        task,
        ["src/parser.py", "README.md"],
    )

    assert result.passed is False
    assert result.out_of_scope_changes == ["README.md"]
