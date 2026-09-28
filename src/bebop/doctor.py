from __future__ import annotations

import os
import logging
import contextlib
import io
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field

import httpx

from bebop.adapters.ao import AOClient, AOError, discover_ao_base_url
from bebop.repo_context import find_grep_ast_command
from bebop.runtime import init_dbos


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    blocker: str | None = None


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def blockers(self) -> list[str]:
        return [check.blocker for check in self.checks if check.blocker]


def run_doctor() -> DoctorReport:
    report = DoctorReport()
    ao_base_url: str | None = None
    ao_client: AOClient | None = None
    projects: list[object] = []

    report.checks.append(_python_check())
    report.checks.append(_command_check("Git", "git", ["git", "--version"], True))

    try:
        ao_base_url = discover_ao_base_url()
        report.checks.append(Check("AO daemon discovery", True, ao_base_url))
    except Exception as exc:
        report.checks.append(Check("AO daemon discovery", False, str(exc), "AO daemon not discovered"))

    if ao_base_url:
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{ao_base_url.rstrip('/')}/projects")
                response.raise_for_status()
            report.checks.append(Check("AO API reachability", True, ao_base_url))
        except Exception as exc:
            report.checks.append(Check("AO API reachability", False, _short(exc), "AO API unreachable"))

        try:
            ao_client = AOClient(ao_base_url, timeout=5)
            projects = ao_client.list_projects()
            detail = f"{len(projects)} project(s)"
            report.checks.append(Check("AO project listing", True, detail))
        except Exception as exc:
            report.checks.append(Check("AO project listing", False, _short(exc), "AO project listing failed"))
    else:
        report.checks.append(Check("AO API reachability", False, "AO base URL unavailable", "AO API unreachable"))
        report.checks.append(Check("AO project listing", False, "AO base URL unavailable", "AO project listing failed"))

    report.checks.append(_command_check("Agent Orchestrator installed/running", "ao", ["ao", "--version"], False))
    report.checks.append(_grep_ast_check())
    report.checks.append(_dbos_check())
    report.checks.append(_planner_check())
    report.checks.append(_shell_check())
    report.checks.append(_git_worktree_check())
    route_checks = [
        _opencode_ollama_readiness(ao_client, projects),
        _opencode_groq_readiness(ao_client, projects),
        _codex_readiness(ao_client, projects),
        _antigravity_readiness(ao_client, projects),
    ]
    report.checks.extend(route_checks)
    if not any(check.ok for check in route_checks):
        report.checks.append(
            Check(
                "Execution route availability",
                False,
                "no configured route is ready",
                "No usable Bebop execution route",
            )
        )
    else:
        report.checks.append(Check("Execution route availability", True, "at least one route ready"))

    if ao_client is not None:
        ao_client.close()
    return report


def _python_check() -> Check:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 11)
    return Check("Python/version", ok, version, None if ok else "Python 3.11+ required")


def _command_check(
    name: str,
    command_name: str,
    command: list[str],
    blocker: bool,
    *,
    alt: str | None = None,
) -> Check:
    executable = shutil.which(command_name) or (shutil.which(alt) if alt else None)
    if not executable:
        return Check(name, False, f"{command_name} not found", f"{name} unavailable" if blocker else None)
    try:
        resolved_command = [executable, *command[1:]]
        completed = subprocess.run(
            resolved_command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return Check(name, False, _short(exc), f"{name} unavailable" if blocker else None)
    detail = (completed.stdout or completed.stderr).strip().splitlines()
    ok = completed.returncode == 0
    return Check(name, ok, detail[0] if detail else executable, None if ok or not blocker else f"{name} unavailable")


def _ao_route_check(name: str, client: AOClient | None, harness: str, projects: list[object]) -> Check:
    if client is None:
        return Check(name, False, "AO unavailable", f"{name} unavailable")
    if not projects:
        return Check(name, False, "no AO projects available", f"{name} unavailable")
    try:
        sessions = client.list_sessions(getattr(projects[0], "id", None))
    except Exception as exc:
        return Check(name, False, _short(exc), f"{name} unavailable")
    seen = any(str(session.get("harness", "")).casefold() == harness for session in sessions)
    detail = "route can be requested; no live session found" if not seen else "live session found"
    return Check(name, True, detail)


def _ao_harness_available(client: AOClient | None, harness: str, projects: list[object]) -> tuple[bool, str]:
    check = _ao_route_check(f"AO/{harness}", client, harness, projects)
    return check.ok, check.detail


def _opencode_ollama_readiness(client: AOClient | None, projects: list[object]) -> Check:
    model = os.getenv("BEBOP_OLLAMA_MODEL", "")
    ao_ok, ao_detail = _ao_harness_available(client, "opencode", projects)
    opencode = _opencode_model_check(model)
    ollama = _ollama_check(model)
    ok = ao_ok and opencode.ok and ollama.ok and model == "ollama/qwen3:8b"
    details = [
        f"AO: {ao_detail}",
        f"model: {model or 'missing'}",
        f"OpenCode: {opencode.detail}",
        f"Ollama: {ollama.detail}",
    ]
    if model and model != "ollama/qwen3:8b":
        details.append("expected ollama/qwen3:8b")
    return Check("Route readiness: OpenCode/Ollama", ok, "; ".join(details))


def _opencode_groq_readiness(client: AOClient | None, projects: list[object]) -> Check:
    model = os.getenv("BEBOP_GROQ_MODEL", "")
    ao_ok, ao_detail = _ao_harness_available(client, "opencode", projects)
    opencode = _opencode_model_check(model)
    key_ok = bool(os.getenv("GROQ_API_KEY"))
    ok = ao_ok and opencode.ok and key_ok and model == "groq/openai/gpt-oss-120b"
    details = [
        f"AO: {ao_detail}",
        f"OpenCode: {opencode.detail}",
        f"GROQ_API_KEY: {'set' if key_ok else 'missing'}",
        f"model: {model or 'missing'}",
    ]
    if model and model != "groq/openai/gpt-oss-120b":
        details.append("expected groq/openai/gpt-oss-120b")
    return Check("Route readiness: OpenCode/Groq", ok, "; ".join(details))


def _opencode_model_check(model: str) -> Check:
    executable = shutil.which("opencode")
    if not executable:
        return Check("OpenCode model registry", False, "opencode not found")
    if not model:
        return Check("OpenCode model registry", False, "model missing")
    try:
        completed = subprocess.run(
            [executable, "models"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return Check("OpenCode model registry", False, _short(exc))
    output = f"{completed.stdout}\n{completed.stderr}"
    ok = completed.returncode == 0 and model in output
    return Check("OpenCode model registry", ok, "model found" if ok else "model not found")


def _codex_readiness(client: AOClient | None, projects: list[object]) -> Check:
    ao_ok, ao_detail = _ao_harness_available(client, "codex", projects)
    cli = _command_check("Codex CLI", "codex", ["codex", "--version"], False)
    auth = _command_check("Codex auth", "codex", ["codex", "login", "status"], False)
    ok = ao_ok and cli.ok and auth.ok
    detail = f"AO: {ao_detail}; CLI: {cli.detail}; auth: {auth.detail if auth.ok else 'run codex login'}"
    return Check("Route readiness: Codex", ok, detail)


def _antigravity_readiness(client: AOClient | None, projects: list[object]) -> Check:
    ao_ok, ao_detail = _ao_harness_available(client, "agy", projects)
    agy = _command_check("agy CLI", "agy", ["agy", "--help"], False)
    auth = _command_check("agy auth", "agy", ["agy", "models"], False)
    ok = ao_ok and agy.ok and auth.ok
    detail = (
        f"AO: {ao_detail}; agy: {agy.detail}; "
        f"auth: {auth.detail if auth.ok else 'install with irm https://antigravity.google/cli/install.ps1 | iex, then run agy --help for documented auth command'}"
    )
    return Check("Route readiness: Antigravity/agy", ok, detail)


def _dbos_check() -> Check:
    try:
        logging.getLogger("dbos").setLevel(logging.WARNING)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            init_dbos()
    except Exception as exc:
        return Check("DBOS initialization", False, _short(exc), "DBOS initialization failed")
    return Check("DBOS initialization", True, "initialized")


def _grep_ast_check() -> Check:
    command = find_grep_ast_command()
    if not command:
        return Check("grep-ast", False, "grep-ast not found", "grep-ast unavailable")
    try:
        completed = subprocess.run(
            [*command, "--languages"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return Check("grep-ast", False, _short(exc), "grep-ast unavailable")
    detail = command[0]
    ok = completed.returncode == 0
    return Check("grep-ast", ok, detail, None if ok else "grep-ast unavailable")


def _env_check(name: str, blocker: str) -> Check:
    value = os.getenv(name)
    return Check(name, bool(value), "set" if value else "missing", None if value else blocker)


def _ollama_check(configured_model: str | None = None) -> Check:
    model = (configured_model or os.getenv("BEBOP_OLLAMA_MODEL", "")).removeprefix("ollama/").strip()
    if not model:
        return Check("Ollama reachability/model availability", False, "BEBOP_OLLAMA_MODEL missing", "Ollama model missing")
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=2):
            pass
        with httpx.Client(timeout=5) as client:
            response = client.get("http://127.0.0.1:11434/api/tags")
            response.raise_for_status()
            models = {str(item.get("name", "")) for item in response.json().get("models", [])}
        ok = model in models
        return Check("Ollama reachability/model availability", ok, model, None if ok else "Configured Ollama model unavailable")
    except Exception as exc:
        return Check("Ollama reachability/model availability", False, _short(exc), "Ollama unavailable")


def _planner_check() -> Check:
    model = os.getenv("BEBOP_PLANNER_MODEL", "groq:llama-3.3-70b-versatile")
    if model.startswith("groq:") and not os.getenv("GROQ_API_KEY"):
        return Check("planner model/configuration", False, model, "Planner Groq API key missing")
    return Check("planner model/configuration", True, model)


def _shell_check() -> Check:
    shell = os.getenv("BEBOP_VERIFY_SHELL") or ("powershell" if os.name == "nt" else "sh")
    found = shutil.which(shell)
    return Check("verification shell", bool(found), shell, None if found else "Verification shell unavailable")


def _git_worktree_check() -> Check:
    try:
        completed = subprocess.run(
            ["git", "worktree", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return Check("Git worktree/session-shell capability", False, _short(exc), "Git worktree unavailable")
    ok = completed.returncode == 0
    return Check("Git worktree/session-shell capability", ok, "git worktree list", None if ok else "Git worktree unavailable")


def _short(exc: object) -> str:
    text = str(exc).strip().replace("\n", " ")
    return text[:500] if text else exc.__class__.__name__
