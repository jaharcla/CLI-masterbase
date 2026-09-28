from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from bebop.models import (
    AOProject,
    AgentSwitch,
    RouteTarget,
    SessionObservation,
    TaskCapsule,
    WorkerSession,
)


class AOError(RuntimeError):
    pass


def discover_ao_base_url(explicit: str | None = None) -> str:
    if explicit:
        return explicit.rstrip("/")

    env_url = os.getenv("AO_BASE_URL")
    if env_url:
        return env_url.rstrip("/")

    run_file = Path(
        os.getenv("AO_RUN_FILE", str(Path.home() / ".ao" / "running.json"))
    ).expanduser()

    try:
        payload = json.loads(run_file.read_text(encoding="utf-8"))
        port = int(payload["port"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AOError(
            f"Could not discover Agent Orchestrator. Start AO or set AO_BASE_URL. "
            f"Expected run file: {run_file}"
        ) from exc

    if not (1 <= port <= 65535):
        raise AOError(f"Invalid AO daemon port in {run_file}: {port}")

    return f"http://127.0.0.1:{port}/api/v1"


class AOClient:
    """Thin client for Agent Orchestrator's local HTTP daemon."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = discover_ao_base_url(base_url)
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def mux_url(self) -> str:
        parsed = urlsplit(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunsplit((scheme, parsed.netloc, "/mux", "", ""))

    def list_projects(self) -> list[AOProject]:
        body = self._json(self._client.get("/projects"), "AO project list")
        return [AOProject.model_validate(project) for project in body.get("projects", [])]

    def resolve_project(self, selector: str) -> AOProject:
        projects = self.list_projects()
        needle = selector.strip()
        folded = needle.casefold()

        exact_id = [project for project in projects if project.id == needle]
        if len(exact_id) == 1:
            return exact_id[0]

        exact_name = [project for project in projects if project.name.casefold() == folded]
        if len(exact_name) == 1:
            return exact_name[0]
        if len(exact_name) > 1:
            raise AOError(f"AO project name is ambiguous: {selector!r}")

        normalized = os.path.normcase(os.path.abspath(os.path.expanduser(needle)))
        path_matches = [
            project
            for project in projects
            if project.path
            and os.path.normcase(os.path.abspath(os.path.expanduser(project.path))) == normalized
        ]
        if len(path_matches) == 1:
            return path_matches[0]

        available = ", ".join(f"{p.id} ({p.name})" for p in projects) or "none"
        raise AOError(f"AO project not found: {selector!r}. Available: {available}")

    def list_sessions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        params = {"project": project_id} if project_id else None
        body = self._json(self._client.get("/sessions", params=params), "AO session list")
        return list(body.get("sessions", []))

    def spawn(
        self,
        task: TaskCapsule,
        target: RouteTarget,
        project_id: str,
        *,
        deliver_prompt: bool = True,
    ) -> WorkerSession:
        display_name = _display_name(task)

        for existing in self.list_sessions(project_id):
            if existing.get("displayName") == display_name and not existing.get("isTerminated", False):
                return self._worker_session(existing, task, target, project_id)

        payload: dict[str, Any] = {
            "projectId": project_id,
            "kind": "worker",
            "harness": target.harness,
            "mode": target.mode,
            "displayName": display_name,
            "approvalMode": target.approval_mode,
        }
        if deliver_prompt:
            payload["prompt"] = render_task_capsule(task)

        model = self._resolve_model(target)
        if model:
            payload["model"] = model
        if target.effort:
            payload["effort"] = target.effort

        body = self._json(self._client.post("/sessions", json=payload), "AO spawn")
        session = body.get("session", body)
        return self._worker_session(session, task, target, project_id, raw=body)

    def get_session(self, session_id: str) -> dict[str, Any]:
        body = self._json(
            self._client.get(f"/sessions/{quote(session_id, safe='')}"),
            "AO session read",
        )
        return dict(body.get("session", body))

    def changed_paths(
        self,
        session_id: str,
        *,
        ignored_commits: set[str] | None = None,
    ) -> list[str]:
        escaped = quote(session_id, safe="")
        body = self._json(
            self._client.get(f"/sessions/{escaped}/workspace/files"),
            "AO workspace file list",
        )

        ignored = {sha.lower() for sha in (ignored_commits or set())}
        paths: list[str] = []

        # Current uncommitted state is always part of this task.
        sections = body.get("sections") or {}
        for key in ("staged", "unstaged", "untracked"):
            for file in sections.get(key, []) or []:
                path = str(file.get("path", ""))
                if path:
                    paths.append(path)

        # Committed-since-base changes are included unless the commit is a known
        # verified dependency imported before this task began.
        for commit in body.get("commits", []) or []:
            sha = str(commit.get("sha", "")).lower()
            if sha and sha in ignored:
                continue
            for file in commit.get("files", []) or []:
                path = str(file.get("path", ""))
                if path:
                    paths.append(path)

        if sections or body.get("commits") is not None:
            return sorted({path.replace("\\", "/") for path in paths})

        # Compatibility fallback for older AO builds.
        for file in body.get("files", []):
            path = str(file.get("path", ""))
            status = str(file.get("status", ""))
            if path and status != "unmodified":
                paths.append(path)
        return sorted({path.replace("\\", "/") for path in paths})

    def workspace_paths(self, session_id: str) -> list[str]:
        escaped = quote(session_id, safe="")
        body = self._json(
            self._client.get(f"/sessions/{escaped}/workspace/files"),
            "AO workspace file list",
        )
        paths: list[str] = []
        for file in body.get("files", []):
            path = str(file.get("path", ""))
            status = str(file.get("status", ""))
            if path and status != "deleted":
                paths.append(path.replace("\\", "/"))
        return sorted(set(paths))

    def list_agent_switches(self, session_id: str) -> list[AgentSwitch]:
        escaped = quote(session_id, safe="")
        body = self._json(
            self._client.get(f"/sessions/{escaped}/agent-switches"),
            "AO agent switch list",
        )
        switches: list[AgentSwitch] = []
        for item in body.get("switches", []):
            payload = dict(item)
            payload["raw"] = dict(item)
            switches.append(AgentSwitch.model_validate(payload))
        return switches

    def switch_agent(
        self,
        session_id: str,
        target: RouteTarget,
        *,
        idempotency_key: str,
        timeout_seconds: float = 600.0,
        poll_seconds: float = 0.5,
    ) -> AgentSwitch:
        if target.harness not in {"codex", "agy", "claude-code", "fx"}:
            raise AOError(
                f"AO in-place agent switching does not support target harness "
                f"{target.harness!r}"
            )
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise AOError("AO agent switch idempotency key must be 1..128 characters")

        escaped = quote(session_id, safe="")
        payload: dict[str, Any] = {
            "targetHarness": target.harness,
            "idempotencyKey": key,
        }
        if target.model:
            payload["model"] = target.model

        body = self._json(
            self._client.post(f"/sessions/{escaped}/switch-agent", json=payload),
            "AO agent switch",
        )
        raw_switch = dict(body.get("switch", body))
        raw_switch["raw"] = dict(raw_switch)
        switch = AgentSwitch.model_validate(raw_switch)
        if switch.state in {"completed", "failed"}:
            return switch

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for candidate in self.list_agent_switches(session_id):
                if candidate.id != switch.id:
                    continue
                if candidate.state in {"completed", "failed"}:
                    return candidate
            time.sleep(poll_seconds)

        raise AOError(
            f"AO agent switch {switch.id} did not finish within "
            f"{timeout_seconds:.0f}s"
        )

    def open_shell_terminal(
        self,
        session_id: str,
        *,
        shell: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"sessionId": session_id}
        if shell:
            payload["shell"] = shell

        body = self._json(
            self._client.post("/shell-terminals", json=payload),
            "AO shell terminal open",
        )
        terminal = dict(body.get("shellTerminal", body))
        if not terminal.get("handleId"):
            raise AOError("AO shell terminal response did not include handleId")
        return terminal

    def close_shell_terminal(self, handle_id: str) -> None:
        response = self._client.delete(f"/shell-terminals/{quote(handle_id, safe='')}")
        if response.status_code == 404:
            return
        self._json(response, "AO shell terminal close", allow_empty=True)

    def observe_until_settled(
        self,
        session_id: str,
        *,
        timeout_seconds: float = 900.0,
        poll_seconds: float = 2.0,
        after_activity_at: str | None = None,
        require_progress: bool = False,
        ignored_commits: set[str] | None = None,
    ) -> SessionObservation:
        deadline = time.monotonic() + timeout_seconds
        progressed = not require_progress

        while True:
            session = self.get_session(session_id)
            activity = session.get("activity") or {}
            activity_state = str(activity.get("state", ""))
            activity_at = str(activity.get("lastActivityAt", ""))
            provision_state = str(session.get("provisionState", "") or "ready")
            terminated = bool(session.get("isTerminated", False))

            if provision_state == "failed":
                raise AOError(
                    f"AO session {session_id} failed to provision: "
                    f"{session.get('provisionError', 'unknown error')}"
                )

            if require_progress and (
                activity_state == "active"
                or (activity_at and activity_at != (after_activity_at or ""))
            ):
                progressed = True

            settled = terminated or activity_state in {
                "idle",
                "waiting_input",
                "blocked",
                "exited",
            }
            if settled and progressed:
                return SessionObservation(
                    session_id=session_id,
                    status=str(session.get("status", "")),
                    activity_state=activity_state,
                    provision_state=provision_state,
                    is_terminated=terminated,
                    changed_paths=self.changed_paths(session_id, ignored_commits=ignored_commits),
                    raw_session=session,
                )

            if time.monotonic() >= deadline:
                detail = " after feedback" if require_progress else ""
                raise AOError(f"Timed out waiting for AO session {session_id}{detail}")

            time.sleep(poll_seconds)

    def send(self, session_id: str, message: str) -> None:
        session = self.get_session(session_id)
        activity = session.get("activity") or {}
        if activity.get("state") == "blocked":
            raise AOError(
                f"Refusing to inject input into blocked AO session {session_id}; "
                "a human decision is pending."
            )

        self._json(
            self._client.post(
                f"/sessions/{quote(session_id, safe='')}/send",
                json={"message": message},
            ),
            "AO send",
            allow_empty=True,
        )

    def kill(self, session_id: str) -> None:
        self._json(
            self._client.post(f"/sessions/{quote(session_id, safe='')}/kill"),
            "AO kill",
            allow_empty=True,
        )

    def _resolve_model(self, target: RouteTarget) -> str | None:
        if target.model:
            return target.model
        if target.harness != "opencode" or not target.provider:
            return None

        env_name = f"BEBOP_{target.provider.upper()}_MODEL"
        model = os.getenv(env_name)
        if not model:
            raise AOError(
                f"{env_name} is required for the OpenCode/{target.provider} route. "
                "Set it to the exact model identifier OpenCode accepts."
            )
        return model

    def _worker_session(
        self,
        session: dict[str, Any],
        task: TaskCapsule,
        target: RouteTarget,
        project_id: str,
        *,
        raw: dict[str, Any] | None = None,
    ) -> WorkerSession:
        session_id = str(session.get("id") or session.get("sessionId") or "")
        if not session_id:
            raise AOError("AO session response did not include a session id")
        return WorkerSession(
            session_id=session_id,
            project_id=project_id,
            route=target,
            raw=raw or {"session": session},
        )

    @staticmethod
    def _json(
        response: httpx.Response,
        operation: str,
        *,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        if response.is_error:
            raise AOError(f"{operation} failed ({response.status_code}): {response.text}")
        if allow_empty and not response.content:
            return {}
        try:
            return dict(response.json())
        except (ValueError, TypeError) as exc:
            if allow_empty:
                return {}
            raise AOError(f"{operation} returned invalid JSON") from exc


def _display_name(task: TaskCapsule) -> str:
    if task.run_id:
        marker = f"[bebop:{task.run_id}:{task.id}] "
    else:
        marker = f"[bebop:{task.id}] "
    return (marker + task.title)[:100]


def render_task_capsule(task: TaskCapsule) -> str:
    sections = [
        f"TASK\n{task.title}",
        f"OBJECTIVE\n{task.objective}",
    ]
    if task.dependencies:
        sections.append("DEPENDENCIES\n" + "\n".join(task.dependencies))
    if task.relevant_files:
        sections.append("RELEVANT FILES\n" + "\n".join(task.relevant_files))
    if task.known_decisions:
        sections.append("KNOWN DECISIONS\n" + "\n".join(task.known_decisions))
    if task.allowed_paths:
        sections.append("ALLOWED PATHS\n" + "\n".join(task.allowed_paths))
    if task.protected_paths:
        sections.append("PROTECTED PATHS\n" + "\n".join(task.protected_paths))
    if task.acceptance_commands:
        sections.append(
            "ACCEPTANCE CHECKS\n"
            + "\n".join(task.acceptance_commands)
            + "\nThese are acceptance criteria, not permission to weaken or rewrite them."
        )
    sections.append(
        "YOUR JOB\n"
        "Perform only this bounded task. Report blockers instead of broadening scope."
    )
    return "\n\n".join(sections)
