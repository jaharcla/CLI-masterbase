from __future__ import annotations


def discover_verification_commands(paths: list[str]) -> list[str]:
    """Return conservative repo-native verification commands from file layout.

    Explicit task acceptance commands always override this registry.
    """
    normalized = {path.replace("\\", "/").lstrip("./") for path in paths}
    names = {path.rsplit("/", 1)[-1] for path in normalized}
    commands: list[str] = []

    has_tests_dir = any(
        path == "tests" or path.startswith("tests/")
        for path in normalized
    )
    has_python = (
        "pyproject.toml" in normalized
        or "pytest.ini" in normalized
        or "setup.cfg" in normalized
        or "setup.py" in normalized
    )
    if has_python and has_tests_dir:
        commands.append("pytest -q")

    if "ruff.toml" in normalized or ".ruff.toml" in normalized:
        commands.append("ruff check .")

    if "go.mod" in normalized:
        commands.append("go test ./...")

    if "Cargo.toml" in normalized:
        commands.append("cargo test --quiet")

    if "package.json" in normalized:
        # npm's --if-present avoids manufacturing a failure when the repo does
        # not define a given script, while still running repo-native checks when
        # they exist.
        commands.extend(
            [
                "npm run test --if-present",
                "npm run lint --if-present",
                "npm run build --if-present",
            ]
        )

    has_dotnet = any(
        name.endswith(".sln") or name.endswith(".csproj")
        for name in names
    )
    if has_dotnet:
        commands.append("dotnet test")

    return _dedupe(commands)


def _dedupe(commands: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for command in commands:
        if command not in seen:
            seen.add(command)
            result.append(command)
    return result
