from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Worktree:
    task_id: str
    branch: str
    path: Path


class WorktreeManager:
    """Thin wrapper around native git worktree operations."""

    def __init__(self, repo_root: Path, worktree_root: Path | None = None):
        self.repo_root = repo_root.resolve()
        self.worktree_root = (
            worktree_root.resolve()
            if worktree_root is not None
            else self.repo_root / ".bebop" / "worktrees"
        )
        self.worktree_root.mkdir(parents=True, exist_ok=True)

    def create(self, task_id: str, base_ref: str) -> Worktree:
        branch = f"bebop/task/{task_id}"
        path = self.worktree_root / task_id
        subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(path), base_ref],
            cwd=self.repo_root,
            check=True,
        )
        return Worktree(task_id=task_id, branch=branch, path=path)

    def remove(self, worktree: Worktree, force: bool = False) -> None:
        argv = ["git", "worktree", "remove"]
        if force:
            argv.append("--force")
        argv.append(str(worktree.path))
        subprocess.run(argv, cwd=self.repo_root, check=True)
