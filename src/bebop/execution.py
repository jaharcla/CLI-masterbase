from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from bebop.models import WorkerResult


@dataclass(slots=True)
class ProcessSpec:
    argv: Sequence[str]
    cwd: Path
    timeout_seconds: int = 900


class NativeProcessRunner:
    """Minimal subprocess runner used by local verification and CLI workers."""

    def run(self, spec: ProcessSpec) -> WorkerResult:
        try:
            completed = subprocess.run(
                list(spec.argv),
                cwd=spec.cwd,
                capture_output=True,
                text=True,
                timeout=spec.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return WorkerResult(
                status="failed",
                summary="Process timed out",
                exit_code=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                problems=[f"Timeout after {spec.timeout_seconds}s"],
            )

        return WorkerResult(
            status="complete" if completed.returncode == 0 else "failed",
            summary=f"Process exited with code {completed.returncode}",
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            commands_run=[" ".join(spec.argv)],
        )
