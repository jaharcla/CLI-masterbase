from __future__ import annotations

import os
from typing import Any

import httpx

from bebop.models import RouteTarget, TaskCapsule, WorkerSession


class AOError(RuntimeError):
    pass


class AOClient:
    """Thin client for Agent Orchestrator's documented local HTTP API."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.getenv("AO_BASE_URL", "http://127.0.0.1:7777/api/v1")).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def spawn(self, task: TaskCapsule, target: RouteTarget) -> WorkerSession:
        payload: dict[str, Any] = {
            "projectId": task.project_id,
            "kind": "worker",
            "harness": target.harness,
            "mode": target.mode,
            "prompt": render_task_capsule(task),
            "displayName": task.title[:100],
            "approvalMode": target.approval_mode,
        }
        if target.model:
            payload["model"] = target.model
        if target.effort:
            payload["effort"] = target.effort

        response = self._client.post("/sessions", json=payload)
        if response.is_error:
            raise AOError(f"AO spawn failed ({response.status_code}): {response.text}")

        body = response.json()
        session = body.get("session", body)
        session_id = str(session.get("id") or session.get("sessionId") or "")
        if not session_id:
            raise AOError("AO spawn response did not include a session id")

        return WorkerSession(
            session_id=session_id,
            project_id=task.project_id,
            route=target,
            raw=body,
        )

    def get_session(self, session_id: str) -> dict[str, Any]:
        response = self._client.get(f"/sessions/{session_id}")
        if response.is_error:
            raise AOError(f"AO session read failed ({response.status_code}): {response.text}")
        return response.json()

    def send(self, session_id: str, message: str) -> None:
        response = self._client.post(f"/sessions/{session_id}/send", json={"message": message})
        if response.is_error:
            raise AOError(f"AO send failed ({response.status_code}): {response.text}")

    def kill(self, session_id: str) -> None:
        response = self._client.post(f"/sessions/{session_id}/kill")
        if response.is_error:
            raise AOError(f"AO kill failed ({response.status_code}): {response.text}")


def render_task_capsule(task: TaskCapsule) -> str:
    sections = [
        f"TASK\n{task.title}",
        f"OBJECTIVE\n{task.objective}",
    ]
    if task.relevant_files:
        sections.append("RELEVANT FILES\n" + "\n".join(task.relevant_files))
    if task.known_decisions:
        sections.append("KNOWN DECISIONS\n" + "\n".join(task.known_decisions))
    if task.allowed_paths:
        sections.append("ALLOWED PATHS\n" + "\n".join(task.allowed_paths))
    if task.protected_paths:
        sections.append("PROTECTED PATHS\n" + "\n".join(task.protected_paths))
    if task.acceptance_commands:
        sections.append("ACCEPTANCE CHECKS\n" + "\n".join(task.acceptance_commands))
    sections.append("YOUR JOB\nPerform only this bounded task. Report blockers instead of broadening scope.")
    return "\n\n".join(sections)
