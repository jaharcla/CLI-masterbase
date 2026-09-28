from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bebop.execution import NativeProcessRunner, ProcessSpec


@dataclass(slots=True)
class VerificationResult:
    passed: bool
    commands: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class Verifier:
    """Runs acceptance commands independently of the implementation worker."""

    def __init__(self, runner: NativeProcessRunner | None = None):
        self.runner = runner or NativeProcessRunner()

    def verify(
        self,
        cwd: Path,
        commands: list[list[str]],
        timeout_seconds: int = 900,
    ) -> VerificationResult:
        result = VerificationResult(passed=True)

        for argv in commands:
            run = self.runner.run(
                ProcessSpec(
                    argv=argv,
                    cwd=cwd,
                    timeout_seconds=timeout_seconds,
                )
            )
            rendered = " ".join(argv)
            result.commands.append(rendered)
            if run.exit_code != 0:
                result.passed = False
                result.failures.append(
                    f"{rendered}: {run.stderr.strip() or run.stdout.strip()}"
                )

        return result
