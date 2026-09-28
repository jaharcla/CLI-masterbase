from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from bebop.adapters.ao import AOClient
from bebop.planner import plan_goal
from bebop.repo_context import build_repo_context
from bebop.runtime import init_dbos
from bebop.workflow import execute_goal


def create_smoke_fixture() -> Path:
    root = Path(tempfile.mkdtemp(prefix="bebop-smoke-"))
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath = [\".\"]\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Bebop Smoke",
            "-c",
            "user.email=bebop-smoke@example.invalid",
            "commit",
            "-m",
            "Initial smoke fixture",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return root


def run_smoke_test(project: str | None = None) -> dict:
    fixture = create_smoke_fixture()
    selector = project or str(fixture)
    goal = "Add a subtract function to src/calc.py with a pytest covering it."
    client = AOClient()
    try:
        ao_project = client.resolve_project(selector)
    finally:
        client.close()
    context = build_repo_context(ao_project.path, goal)
    plan = plan_goal(goal, ao_project.id, context)
    init_dbos()
    return execute_goal(plan.model_dump())
