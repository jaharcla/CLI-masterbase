from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from websockets.sync.client import connect

from bebop.adapters.ao import AOClient, AOError
from bebop.models import CommandResult


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class AOTerminalVerifier:
    """Run acceptance commands in AO's session-scoped shell/worktree."""

    def __init__(
        self,
        client: AOClient,
        *,
        shell: str | None = None,
        connect_fn: Callable[..., Any] = connect,
        output_limit: int = 64 * 1024,
    ):
        self.client = client
        self.shell = shell or os.getenv("BEBOP_VERIFY_SHELL") or (
            "powershell" if os.name == "nt" else None
        )
        self.connect_fn = connect_fn
        self.output_limit = output_limit

    def run_commands(
        self,
        session_id: str,
        commands: list[str],
        *,
        timeout_seconds: float = 900.0,
    ) -> list[CommandResult]:
        results: list[CommandResult] = []
        for command in commands:
            result = self.run_command(
                session_id,
                command,
                timeout_seconds=timeout_seconds,
            )
            results.append(result)
            if not result.passed:
                break
        return results

    def run_command(
        self,
        session_id: str,
        command: str,
        *,
        timeout_seconds: float = 900.0,
    ) -> CommandResult:
        command = command.strip()
        if not command:
            raise AOError("Acceptance command cannot be empty")
        if "\n" in command or "\r" in command:
            raise AOError("Acceptance commands must be single-line commands")

        terminal = self.client.open_shell_terminal(
            session_id,
            shell=self.shell,
        )
        handle_id = str(terminal["handleId"])
        marker = f"__BEBOP_EXIT_{uuid.uuid4().hex}__"
        wrapped, newline = _wrap_command(command, marker, self.shell)
        started = time.monotonic()
        output = bytearray()
        exit_code: int | None = None

        try:
            with self.connect_fn(
                self.client.mux_url(),
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                proxy=None,
            ) as websocket:
                websocket.send(
                    json.dumps(
                        {
                            "ch": "terminal",
                            "type": "open",
                            "id": handle_id,
                            "cols": 120,
                            "rows": 40,
                        }
                    )
                )
                self._wait_opened(websocket, handle_id, timeout_seconds)

                encoded = base64.b64encode((wrapped + newline).encode("utf-8")).decode("ascii")
                websocket.send(
                    json.dumps(
                        {
                            "ch": "terminal",
                            "type": "data",
                            "id": handle_id,
                            "data": encoded,
                        }
                    )
                )

                deadline = time.monotonic() + timeout_seconds
                marker_re = re.compile(re.escape(marker.encode("ascii")) + rb":(-?\d+)")

                while time.monotonic() < deadline:
                    remaining = max(0.05, deadline - time.monotonic())
                    frame = _receive_frame(websocket, remaining)
                    if frame.get("ch") != "terminal":
                        continue
                    if frame.get("id") not in {None, handle_id}:
                        continue
                    if frame.get("type") == "error":
                        raise AOError(
                            f"AO terminal error: {frame.get('error', 'unknown terminal error')}"
                        )
                    if frame.get("type") == "exited":
                        raise AOError("AO verification shell exited before reporting an exit code")
                    if frame.get("type") != "data" or not frame.get("data"):
                        continue

                    try:
                        chunk = base64.b64decode(str(frame["data"]))
                    except (ValueError, TypeError) as exc:
                        raise AOError("AO terminal returned invalid base64 data") from exc

                    output.extend(chunk)
                    if len(output) > self.output_limit * 2:
                        del output[: len(output) - self.output_limit * 2]

                    match = marker_re.search(output)
                    if match:
                        exit_code = int(match.group(1))
                        break

                if exit_code is None:
                    raise AOError(f"Acceptance command timed out after {timeout_seconds:.0f}s")

                try:
                    websocket.send(
                        json.dumps(
                            {
                                "ch": "terminal",
                                "type": "close",
                                "id": handle_id,
                            }
                        )
                    )
                except Exception:
                    pass
        finally:
            try:
                self.client.close_shell_terminal(handle_id)
            except AOError:
                pass

        cleaned = _clean_output(bytes(output), marker)
        return CommandResult(
            command=command,
            exit_code=exit_code,
            passed=exit_code == 0,
            output=cleaned[-self.output_limit :],
            duration_seconds=round(time.monotonic() - started, 3),
        )

    @staticmethod
    def _wait_opened(websocket: Any, handle_id: str, timeout_seconds: float) -> None:
        deadline = time.monotonic() + min(timeout_seconds, 20.0)
        while time.monotonic() < deadline:
            frame = _receive_frame(websocket, max(0.05, deadline - time.monotonic()))
            if frame.get("ch") != "terminal":
                continue
            if frame.get("id") not in {None, handle_id}:
                continue
            if frame.get("type") == "opened":
                return
            if frame.get("type") == "error":
                raise AOError(
                    f"AO terminal open failed: {frame.get('error', 'unknown terminal error')}"
                )
        raise AOError("Timed out attaching to AO verification shell")


def _receive_frame(websocket: Any, timeout: float) -> dict[str, Any]:
    try:
        message = websocket.recv(timeout=timeout)
    except TimeoutError as exc:
        raise AOError("Timed out waiting for AO terminal output") from exc
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    try:
        value = json.loads(message)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AOError("AO terminal mux returned invalid JSON") from exc
    return dict(value)


def _wrap_command(command: str, marker: str, shell: str | None) -> tuple[str, str]:
    normalized = (shell or "").lower()

    if normalized in {"powershell", "pwsh"}:
        wrapped = (
            f"& {{ {command} }}; "
            "$__bebop_ok=$?; "
            "$__bebop_code = if ($__bebop_ok) { 0 } "
            "elseif ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { $LASTEXITCODE } "
            "else { 1 }; "
            f'Write-Output "{marker}:$__bebop_code"'
        )
        return wrapped, "\r\n"

    if normalized == "cmd":
        raise AOError(
            "cmd verification is not supported yet; use powershell, pwsh, git-bash, or a POSIX shell"
        )

    wrapped = (
        f"( {command} ); __bebop_code=$?; "
        f"printf '\\n{marker}:%s\\n' \"$__bebop_code\""
    )
    return wrapped, "\n"


def _clean_output(raw: bytes, marker: str) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = _ANSI_RE.sub("", text)
    text = re.sub(re.escape(marker) + r":-?\d+", "", text)
    return text.replace("\r", "").strip()
