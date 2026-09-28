from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "with", "finish", "fix", "implement", "improve", "update",
}


def goal_search_pattern(goal: str, max_terms: int = 8) -> str:
    terms: list[str] = []
    seen: set[str] = set()

    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_-]{2,}", goal):
        lowered = token.lower()
        if lowered in _STOPWORDS or lowered in seen:
            continue
        seen.add(lowered)
        terms.append(re.escape(token))
        if len(terms) >= max_terms:
            break

    return "|".join(terms) if terms else re.escape(goal.strip() or "TODO")


def build_repo_context(
    repo_root: str | Path,
    goal: str,
    *,
    max_chars: int = 14000,
    timeout_seconds: float = 20.0,
) -> str:
    """Build compact AST-aware context by delegating search to grep-ast."""
    root = Path(repo_root).expanduser().resolve()
    if not root.is_dir():
        return f"Repository path unavailable: {root}"

    executable = shutil.which("grep-ast") or shutil.which("gast")
    if not executable:
        return "grep-ast is not available in the Bebop environment."

    pattern = goal_search_pattern(goal)
    try:
        completed = subprocess.run(
            [executable, "--no-color", pattern],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"grep-ast context unavailable: {exc}"

    output = completed.stdout.strip()
    if not output:
        stderr = completed.stderr.strip()
        return (
            "grep-ast found no matching source context."
            + (f" Diagnostic: {stderr[-1000:]}" if stderr else "")
        )

    if len(output) > max_chars:
        output = output[:max_chars] + "\n...[grep-ast context truncated]"

    return output
