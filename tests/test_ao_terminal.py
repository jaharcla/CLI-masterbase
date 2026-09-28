import base64
import json

from bebop.adapters.ao_terminal import AOTerminalVerifier, _wrap_command


class FakeAOClient:
    def __init__(self):
        self.closed = []

    def open_shell_terminal(self, session_id, *, shell=None):
        assert session_id == "s-1"
        return {"handleId": "term-1", "workingDir": "C:/repo/worktree"}

    def close_shell_terminal(self, handle_id):
        self.closed.append(handle_id)

    def mux_url(self):
        return "ws://ao.test/mux"


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.recv_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self, timeout=None):
        self.recv_count += 1
        if self.recv_count == 1:
            return json.dumps({"ch": "terminal", "type": "opened", "id": "term-1"})

        data_frame = next(frame for frame in self.sent if frame["type"] == "data")
        command = base64.b64decode(data_frame["data"]).decode("utf-8")
        start = command.index("__BEBOP_EXIT_")
        end = command.index("__", start + len("__BEBOP_EXIT_")) + 2
        marker = command[start:end]
        payload = base64.b64encode(f"tests passed\r\n{marker}:0\r\n".encode()).decode()
        return json.dumps(
            {"ch": "terminal", "type": "data", "id": "term-1", "data": payload}
        )


def fake_connect(*args, **kwargs):
    return FakeWebSocket()


def test_runs_acceptance_command_through_ao_mux():
    client = FakeAOClient()
    verifier = AOTerminalVerifier(
        client,
        shell="powershell",
        connect_fn=fake_connect,
    )

    result = verifier.run_command("s-1", "pytest -q")

    assert result.passed is True
    assert result.exit_code == 0
    assert "tests passed" in result.output
    assert client.closed == ["term-1"]


def test_powershell_wrapper_reports_exit_marker():
    wrapped, newline = _wrap_command("pytest -q", "__MARKER__", "powershell")

    assert "__MARKER__:$__bebop_code" in wrapped
    assert "$LASTEXITCODE" in wrapped
    assert newline == "\r\n"
