from __future__ import annotations

from pathlib import PurePosixPath

from bebop.models import TaskCapsule, VerificationResult


def check_protected_paths(task: TaskCapsule, changed_paths: list[str]) -> VerificationResult:
    """Policy check only. AO owns the workspace; Bebop owns acceptance policy."""
    protected: list[str] = []

    for changed in changed_paths:
        changed_path = PurePosixPath(changed)
        for pattern in task.protected_paths:
            # MVP supports exact paths and simple directory prefixes ending in /**.
            if pattern.endswith("/**"):
                prefix = PurePosixPath(pattern[:-3])
                if changed_path == prefix or prefix in changed_path.parents:
                    protected.append(changed)
                    break
            elif changed == pattern:
                protected.append(changed)
                break

    return VerificationResult(
        passed=not protected,
        evidence=[f"{len(changed_paths)} changed path(s) inspected"],
        failures=["protected verification artifacts changed"] if protected else [],
        protected_path_changes=protected,
    )
