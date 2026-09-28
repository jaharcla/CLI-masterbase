from __future__ import annotations

import re

from bebop.adapters.ao import AOClient, AOError
from bebop.adapters.ao_terminal import AOTerminalVerifier


_SHA_RE = re.compile(r"\b[0-9a-fA-F]{40,64}\b")


class GitHandoff:
    """Move verified code between AO-owned worktrees using Git commits."""

    def __init__(self, client: AOClient):
        self.verifier = AOTerminalVerifier(client)

    def head(self, session_id: str) -> str:
        rev = self.verifier.run_command(session_id, "git rev-parse HEAD")
        if not rev.passed:
            raise AOError(f"Could not resolve worktree HEAD: {rev.output}")
        matches = _SHA_RE.findall(rev.output)
        if not matches:
            raise AOError("git rev-parse HEAD did not return a commit SHA")
        return matches[-1].lower()

    def conflicted_files(self, session_id: str) -> list[str]:
        result = self.verifier.run_command(
            session_id,
            "git diff --name-only --diff-filter=U",
        )
        if not result.passed:
            raise AOError(f"Could not inspect merge conflicts: {result.output}")
        return sorted(
            {
                line.strip().replace("\\", "/")
                for line in result.output.splitlines()
                if line.strip()
            }
        )

    def apply_commit(
        self,
        session_id: str,
        commit: str,
        *,
        leave_conflict: bool = False,
    ) -> dict:
        if not _SHA_RE.fullmatch(commit):
            raise AOError(f"Invalid dependency commit SHA: {commit!r}")

        ancestor = self.verifier.run_command(
            session_id,
            f"git merge-base --is-ancestor {commit} HEAD",
        )
        if ancestor.passed:
            return {
                "ok": True,
                "commit": commit,
                "already_present": True,
                "head": self.head(session_id),
            }
        if ancestor.exit_code != 1:
            raise AOError(
                f"Could not inspect dependency commit {commit}: {ancestor.output}"
            )

        cherry_pick = self.verifier.run_command(
            session_id,
            f"git cherry-pick {commit}",
        )
        if cherry_pick.passed:
            return {
                "ok": True,
                "commit": commit,
                "already_present": False,
                "head": self.head(session_id),
            }

        conflicts = self.conflicted_files(session_id)
        if leave_conflict and conflicts:
            return {
                "ok": False,
                "conflict": True,
                "commit": commit,
                "conflict_files": conflicts,
                "output": cherry_pick.output,
            }

        self.abort_cherry_pick(session_id)
        raise AOError(
            f"Dependency commit {commit} conflicted in AO worktree: "
            f"{cherry_pick.output}"
        )

    def integrate_commits(self, session_id: str, commits: list[str]) -> str:
        for commit in commits:
            self.apply_commit(session_id, commit)
        return self.head(session_id)

    def abort_cherry_pick(self, session_id: str) -> None:
        abort = self.verifier.run_command(session_id, "git cherry-pick --abort")
        if not abort.passed:
            # There may be no cherry-pick left to abort because an agent already
            # completed it. Only raise when the repository is still conflicted.
            if self.conflicted_files(session_id):
                raise AOError(f"Could not abort conflicted cherry-pick: {abort.output}")

    def continue_cherry_pick(self, session_id: str) -> dict:
        conflicts = self.conflicted_files(session_id)
        if conflicts:
            return {
                "ok": False,
                "conflict": True,
                "conflict_files": conflicts,
                "error": "merge conflict markers remain",
            }

        cherry_pick_head = self.verifier.run_command(
            session_id,
            "git rev-parse -q --verify CHERRY_PICK_HEAD",
        )

        if cherry_pick_head.passed:
            stage = self.verifier.run_command(session_id, "git add -A")
            if not stage.passed:
                return {
                    "ok": False,
                    "error": f"could not stage conflict resolution: {stage.output}",
                }

            continued = self.verifier.run_command(
                session_id,
                (
                    'git -c user.name="Bebop" -c user.email="bebop@local" '
                    "-c core.editor=true cherry-pick --continue"
                ),
            )
            if not continued.passed:
                remaining = self.conflicted_files(session_id)
                return {
                    "ok": False,
                    "conflict": bool(remaining),
                    "conflict_files": remaining,
                    "error": f"could not continue cherry-pick: {continued.output}",
                }
        elif cherry_pick_head.exit_code not in {1}:
            return {
                "ok": False,
                "error": (
                    "could not inspect cherry-pick state: "
                    f"{cherry_pick_head.output}"
                ),
            }

        status = self.verifier.run_command(session_id, "git status --porcelain")
        if not status.passed:
            return {
                "ok": False,
                "error": f"could not inspect resolved worktree: {status.output}",
            }
        if status.output.strip():
            return {
                "ok": False,
                "error": (
                    "integration worker left uncommitted changes after conflict "
                    f"resolution: {status.output}"
                ),
            }

        return {"ok": True, "head": self.head(session_id)}

    def commit_verified_changes(
        self,
        session_id: str,
        task_id: str,
        baseline_sha: str,
    ) -> str | None:
        if not _SHA_RE.fullmatch(baseline_sha):
            raise AOError(f"Invalid task baseline SHA: {baseline_sha!r}")

        # Agents may create their own commits. Collapse every verified change
        # after the dependency baseline into one canonical handoff commit so
        # downstream tasks inherit exactly this task's verified delta.
        reset = self.verifier.run_command(
            session_id,
            f"git reset --soft {baseline_sha}",
        )
        if not reset.passed:
            raise AOError(f"Could not reset task history to baseline: {reset.output}")

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

        return self.head(session_id)
