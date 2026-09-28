from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from bebop.adapters.ao import AOClient
from bebop.models import GoalPlan, TaskCapsule
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
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/bebop-smoke.git"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", head],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "branch.main.remote", "origin"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "branch.main.merge", "refs/heads/main"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return root


def run_smoke_test(project: str | None = None) -> dict:
    if project is not None:
        raise ValueError(
            "smoke-test always uses a disposable fixture; remove --project to "
            "avoid mutating an unrelated repository"
        )

    fixture = create_smoke_fixture()
    project_id: str | None = None
    client: AOClient | None = None
    try:
        client = AOClient()
        ao_project = client.register_project(
            str(fixture),
            name=f"bebop-smoke-{uuid4().hex[:8]}",
        )
        goal = "Add a subtract function to src/calc.py with a pytest covering it."
        project_id = ao_project.id
        plan = GoalPlan(
            id="smoke-goal",
            goal=goal,
            project=ao_project.id,
            tasks=[
                TaskCapsule(
                    id="T001",
                    title="Add subtract function and test",
                    objective=goal,
                    project=ao_project.id,
                    relevant_files=["src/calc.py"],
                    allowed_paths=["src/calc.py", "tests/test_calc.py"],
                    acceptance_commands=["python -m pytest -q"],
                )
            ],
        )
        init_dbos()
        return execute_goal(plan.model_dump(), uuid4().hex)
    finally:
        if client is not None:
            if project_id:
                client.remove_project(project_id)
            client.close()
        shutil.rmtree(fixture, ignore_errors=True)
