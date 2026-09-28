from __future__ import annotations

from pathlib import PurePosixPath

from bebop.models import TaskCapsule, VerificationResult


def inspect_workspace(task: TaskCapsule, changed_paths: list[str]) -> VerificationResult:
    """Evaluate Bebop-owned policy over AO-reported workspace facts.

    Acceptance commands are intentionally not marked passed here. AO currently
    gives us workspace state but no simple machine-verifiable REST command runner.
    """
    protected: list[str] = []

    for changed in changed_paths:
        changed_path = PurePosixPath(changed)
        for pattern in task.protected_paths:
            if pattern.endswith("/**"):
                prefix = PurePosixPath(pattern[:-3])
                if changed_path == prefix or prefix in changed_path.parents:
                    protected.append(changed)
                    break
            elif changed == pattern:
                protected.append(changed)
                break

    acceptance_pending = bool(task.acceptance_commands)
    failures = ["protected verification artifacts changed"] if protected else []

    return VerificationResult(
        passed=not protected and not acceptance_pending,
        evidence=[f"{len(changed_paths)} changed path(s) inspected through AO"],
        failures=failures,
        protected_path_changes=protected,
        acceptance_pending=acceptance_pending,
    )


# Backward-compatible name for the first bootstrap tests/callers.
check_protected_paths = inspect_workspace
