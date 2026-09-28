from __future__ import annotations

import re

from bebop.adapters.ao import AOClient, AOError
from bebop.adapters.ao_terminal import AOTerminalVerifier


_SHA_RE = re.compile(r"\b[0-9a-fA-F]{40,64}\b")


class GitHandoff:
    """Move verified code between AO-owned worktrees using Git commits."""

    def __init__(self, client: AOClient):
        self.verifier = AOTerminalVerifier(client)

    def integrate_commits(self, session_id: str, commits: list[str]) -> None:
        for commit in commits:
            if not _SHA_RE.fullmatch(commit):
                raise AOError(f"Invalid dependency commit SHA: {commit!r}")

            ancestor = self.verifier.run_command(
                session_id,
                f"git merge-base --is-ancestor {commit} HEAD",
            )
            if ancestor.passed:
                continue
            if ancestor.exit_code not in {1}:
                raise AOError(
                    f"Could not inspect dependency commit {commit}: {ancestor.output}"
                )

            cherry_pick = self.verifier.run_command(
                session_id,
                f"git cherry-pick {commit}",
            )
            if not cherry_pick.passed:
                try:
                    self.verifier.run_command(session_id, "git cherry-pick --abort")
                except AOError:
                    pass
                raise AOError(
                    f"Dependency commit {commit} conflicted in AO worktree: "
                    f"{cherry_pick.output}"
                )

    def commit_verified_changes(self, session_id: str, task_id: str) -> str | None:
        stage = self.verifier.run_command(session_id, "git add -A")
        if not stage.passed:
            raise AOError(f"Could not stage verified task changes: {stage.output}")

        diff = self.verifier.run_command(session_id, "git diff --cached --quiet")
        if diff.passed:
            return None
        if diff.exit_code != 1:
            raise AOError(f"Could not inspect staged task changes: {diff.output}")

        commit = self.verifier.run_command(
            session_id,
            (
                'git -c user.name="Bebop" -c user.email="bebop@local" '
                f'commit -m "bebop({task_id}): verified task"'
            ),
        )
        if not commit.passed:
            raise AOError(f"Could not commit verified task changes: {commit.output}")

        rev = self.verifier.run_command(session_id, "git rev-parse HEAD")
        if not rev.passed:
            raise AOError(f"Could not resolve verified commit SHA: {rev.output}")

        matches = _SHA_RE.findall(rev.output)
        if not matches:
            raise AOError("git rev-parse HEAD did not return a commit SHA")
        return matches[-1].lower()
