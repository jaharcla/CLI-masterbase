from types import SimpleNamespace

from bebop.graph import ordered_verified_commits


def test_verified_commits_follow_dependency_wave_order():
    outcomes = {
        "T1": SimpleNamespace(state="verified", commit_sha="a" * 40),
        "T2": SimpleNamespace(state="verified_after_repair", commit_sha="b" * 40),
        "T3": SimpleNamespace(state="escalated_worker_failed", commit_sha=None),
    }

    commits = ordered_verified_commits(
        [["T1", "T2"], ["T3"]],
        outcomes,
    )

    assert commits == ["a" * 40, "b" * 40]
