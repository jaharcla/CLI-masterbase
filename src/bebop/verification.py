from __future__ import annotations

from pathspec import PathSpec

from bebop.models import CommandResult, TaskCapsule, VerificationResult


def _normalize(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _spec(patterns: list[str]) -> PathSpec | None:
    if not patterns:
        return None
    return PathSpec.from_lines("gitwildmatch", patterns)


def inspect_workspace(task: TaskCapsule, changed_paths: list[str]) -> VerificationResult:
    """Evaluate Bebop-owned path policy over AO-reported current-task edits."""
    changed = [_normalize(path) for path in changed_paths]

    protected_spec = _spec(task.protected_paths)
    protected = (
        [path for path in changed if protected_spec.match_file(path)]
        if protected_spec
        else []
    )

    allowed_spec = _spec(task.allowed_paths)
    out_of_scope = (
        [path for path in changed if not allowed_spec.match_file(path)]
        if allowed_spec
        else []
    )

    acceptance_pending = bool(task.acceptance_commands)
    failures: list[str] = []
    if protected:
        failures.append("protected verification artifacts changed")
    if out_of_scope:
        failures.append("changes outside allowed task paths")

    return VerificationResult(
        passed=not protected and not out_of_scope and not acceptance_pending,
        evidence=[f"{len(changed)} current-task changed path(s) inspected through AO"],
        failures=failures,
        protected_path_changes=protected,
        out_of_scope_changes=out_of_scope,
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
        passed=(
            not policy.protected_path_changes
            and not policy.out_of_scope_changes
            and commands_passed
        ),
        evidence=[
            *policy.evidence,
            f"{len(command_results)}/{len(expected_commands)} acceptance command(s) executed",
        ],
        failures=failures,
        protected_path_changes=policy.protected_path_changes,
        out_of_scope_changes=policy.out_of_scope_changes,
        acceptance_pending=not complete,
        command_results=command_results,
    )


check_protected_paths = inspect_workspace
