from bebop.verifier_registry import discover_verification_commands


def test_python_repo_discovers_pytest():
    commands = discover_verification_commands(
        ["pyproject.toml", "src/app.py", "tests/test_app.py"]
    )
    assert "pytest -q" in commands


def test_node_repo_uses_if_present_scripts():
    commands = discover_verification_commands(
        ["package.json", "src/index.ts", "package-lock.json"]
    )
    assert commands == [
        "npm run test --if-present",
        "npm run lint --if-present",
        "npm run build --if-present",
    ]


def test_multiple_languages_get_multiple_machine_checks():
    commands = discover_verification_commands(
        ["go.mod", "Cargo.toml", "src/main.go"]
    )
    assert commands == ["go test ./...", "cargo test --quiet"]


def test_unknown_repo_does_not_invent_verification():
    assert discover_verification_commands(["README.md", "src/file.txt"]) == []
