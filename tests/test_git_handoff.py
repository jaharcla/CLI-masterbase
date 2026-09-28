from bebop.adapters.git_handoff import GitHandoff
from bebop.models import CommandResult


class FakeVerifier:
    def __init__(self, responses):
        self.responses = list(responses)
        self.commands = []

    def run_command(self, session_id, command):
        self.commands.append(command)
        assert self.responses, f"unexpected command: {command}"
        return self.responses.pop(0)


def result(command, exit_code, output=""):
    return CommandResult(
        command=command,
        exit_code=exit_code,
        passed=exit_code == 0,
        output=output,
    )


def handoff_with(responses):
    handoff = GitHandoff.__new__(GitHandoff)
    handoff.verifier = FakeVerifier(responses)
    return handoff


def test_apply_commit_can_leave_conflict_for_agent_resolution():
    commit = "a" * 40
    handoff = handoff_with(
        [
            result("merge-base", 1),
            result("cherry-pick", 1, "CONFLICT"),
            result("conflicts", 0, "src/a.py\nsrc/b.py\n"),
        ]
    )

    outcome = handoff.apply_commit("s-1", commit, leave_conflict=True)

    assert outcome["ok"] is False
    assert outcome["conflict"] is True
    assert outcome["conflict_files"] == ["src/a.py", "src/b.py"]
    assert all("--abort" not in command for command in handoff.verifier.commands)


def test_continue_cherry_pick_finishes_clean_resolution():
    head = "b" * 40
    handoff = handoff_with(
        [
            result("conflicts", 0, ""),
            result("cherry-pick-head", 0, "c" * 40),
            result("git-add", 0),
            result("continue", 0),
            result("status", 0, ""),
            result("head", 0, head),
        ]
    )

    outcome = handoff.continue_cherry_pick("s-1")

    assert outcome == {"ok": True, "head": head}


def test_continue_cherry_pick_refuses_remaining_conflicts():
    handoff = handoff_with(
        [
            result("conflicts", 0, "src/a.py\n"),
        ]
    )

    outcome = handoff.continue_cherry_pick("s-1")

    assert outcome["ok"] is False
    assert outcome["conflict"] is True
    assert outcome["conflict_files"] == ["src/a.py"]
