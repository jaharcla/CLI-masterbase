import respx
from httpx import Response

from bebop.doctor import _ao_route_check, _ollama_check, _opencode_groq_readiness


class _Socket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


@respx.mock
def test_ollama_check_requires_exact_qwen3_model(monkeypatch):
    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: _Socket())
    respx.get("http://127.0.0.1:11434/api/tags").mock(
        return_value=Response(200, json={"models": [{"name": "qwen3:8b"}]})
    )

    result = _ollama_check("ollama/qwen3:8b")

    assert result.ok is True


def test_groq_readiness_requires_final_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("BEBOP_GROQ_MODEL", "groq/openai/gpt-oss-120b")

    result = _opencode_groq_readiness(None, [])

    assert result.ok is False
    assert "groq/openai/gpt-oss-120b" in result.detail


def test_ao_route_check_labels_preflight_without_claiming_worker_proof():
    class Client:
        def list_sessions(self, project_id):
            return []

    result = _ao_route_check("AO/codex", Client(), "codex", [type("P", (), {"id": "p1"})()])

    assert result.ok is True
    assert "real worker execution not proven" in result.detail
