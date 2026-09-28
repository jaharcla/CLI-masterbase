from __future__ import annotations

from pathlib import PurePosixPath

from bebop.models import CommandResult, TaskCapsule, VerificationResult


def inspect_workspace(task: TaskCapsule, changed_paths: list[str]) -> VerificationResult:
    """Evaluate Bebop-owned policy over AO-reported workspace facts."""
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


def apply_command_results(
    policy: VerificationResult,
    expected_commands: list[str],
    command_results: list[CommandResult],
) -> VerificationResult:
    failures = list(policy.failures)
    failed = [result for result in command_results if not result.passed]
    for result in failed:
        failures.append(
            f"acceptance command failed ({result.exit_code}): {result.command}"
        )

    complete = len(command_results) == len(expected_commands)
    commands_passed = complete and all(result.passed for result in command_results)

    return VerificationResult(
        passed=not policy.protected_path_changes and commands_passed,
        evidence=[
            *policy.evidence,
            f"{len(command_results)}/{len(expected_commands)} acceptance command(s) executed",
        ],
        failures=failures,
        protected_path_changes=policy.protected_path_changes,
        acceptance_pending=not complete,
        command_results=command_results,
    )


# Backward-compatible name for the first bootstrap tests/callers.
check_protected_paths = inspect_workspace
