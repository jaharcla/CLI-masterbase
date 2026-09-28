import json

import pytest
import respx
from httpx import Response

from bebop.adapters.ao import AOClient, AOError, discover_ao_base_url
from bebop.models import RouteTarget, TaskCapsule


def test_discovers_ao_daemon_from_run_file(tmp_path, monkeypatch):
    run_file = tmp_path / "running.json"
    run_file.write_text(json.dumps({"pid": 123, "port": 43210}), encoding="utf-8")
    monkeypatch.delenv("AO_BASE_URL", raising=False)
    monkeypatch.setenv("AO_RUN_FILE", str(run_file))

    assert discover_ao_base_url() == "http://127.0.0.1:43210/api/v1"


@respx.mock
def test_resolves_project_by_name():
    respx.get("http://ao.test/api/v1/projects").mock(
        return_value=Response(
            200,
            json={
                "projects": [
                    {
                        "id": "courseai",
                        "name": "CourseAI",
                        "path": "C:/CourseAI",
                        "kind": "single_repo",
                        "folderMissing": False,
                    }
                ]
            },
        )
    )

    client = AOClient("http://ao.test/api/v1")
    try:
        project = client.resolve_project("CourseAI")
    finally:
        client.close()

    assert project.id == "courseai"


@respx.mock
def test_workspace_files_only_return_changes():
    respx.get("http://ao.test/api/v1/sessions/s-1/workspace/files").mock(
        return_value=Response(
            200,
            json={
                "sessionId": "s-1",
                "files": [
                    {"path": "src/a.py", "status": "modified"},
                    {"path": "src/b.py", "status": "unmodified"},
                    {"path": "tests/test_a.py", "status": "added"},
                ],
            },
        )
    )

    client = AOClient("http://ao.test/api/v1")
    try:
        changed = client.changed_paths("s-1")
    finally:
        client.close()

    assert changed == ["src/a.py", "tests/test_a.py"]


@respx.mock
def test_spawn_reuses_existing_bebop_session(monkeypatch):
    monkeypatch.setenv("BEBOP_OLLAMA_MODEL", "ollama/test-model")
    respx.get("http://ao.test/api/v1/sessions", params={"project": "p1"}).mock(
        return_value=Response(
            200,
            json={
                "sessions": [
                    {
                        "id": "s-existing",
                        "displayName": "[bebop:T1] Implement parser",
                        "isTerminated": False,
                    }
                ]
            },
        )
    )

    task = TaskCapsule(
        id="T1",
        title="Implement parser",
        objective="Implement parser",
        project="p1",
    )
    target = RouteTarget(
        harness="opencode",
        provider="ollama",
        reason="test",
    )

    client = AOClient("http://ao.test/api/v1")
    try:
        session = client.spawn(task, target, "p1")
    finally:
        client.close()

    assert session.session_id == "s-existing"


def test_opencode_route_requires_concrete_model(monkeypatch):
    monkeypatch.delenv("BEBOP_GROQ_MODEL", raising=False)
    client = AOClient("http://ao.test/api/v1")
    try:
        with pytest.raises(AOError):
            client._resolve_model(
                RouteTarget(harness="opencode", provider="groq", reason="test")
            )
    finally:
        client.close()


@respx.mock
def test_switch_agent_polls_same_session_until_completed():
    post = respx.post("http://ao.test/api/v1/sessions/s-1/switch-agent").mock(
        return_value=Response(
            202,
            json={
                "switch": {
                    "id": "sw-1",
                    "sessionId": "s-1",
                    "fromHarness": "opencode",
                    "targetHarness": "codex",
                    "state": "preparing_handoff",
                }
            },
        )
    )
    respx.get("http://ao.test/api/v1/sessions/s-1/agent-switches").mock(
        return_value=Response(
            200,
            json={
                "switches": [
                    {
                        "id": "sw-1",
                        "sessionId": "s-1",
                        "fromHarness": "opencode",
                        "targetHarness": "codex",
                        "state": "completed",
                        "agentHandoffStatus": "received",
                        "semanticHandoffIncluded": True,
                    }
                ]
            },
        )
    )

    client = AOClient("http://ao.test/api/v1")
    try:
        result = client.switch_agent(
            "s-1",
            RouteTarget(harness="codex", effort="medium", reason="escalation"),
            idempotency_key="bebop-T1-esc-1-test",
            poll_seconds=0,
        )
    finally:
        client.close()

    assert result.state == "completed"
    assert result.target_harness == "codex"
    assert json.loads(post.calls[0].request.content) == {
        "targetHarness": "codex",
        "idempotencyKey": "bebop-T1-esc-1-test",
    }


def test_switch_agent_rejects_non_native_target():
    client = AOClient("http://ao.test/api/v1")
    try:
        with pytest.raises(AOError):
            client.switch_agent(
                "s-1",
                RouteTarget(harness="opencode", provider="groq", reason="test"),
                idempotency_key="key",
            )
    finally:
        client.close()
