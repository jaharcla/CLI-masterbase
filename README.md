# Bebop Code Hub

Bebop is a thin routing and verification layer for existing coding-agent infrastructure.

It does **not** reimplement worktrees, agent process supervision, durable session state, or coding-agent harnesses.

## Stack

- **Agent Orchestrator**: workers, sessions, worktrees, Codex/Copilot/OpenCode execution
- **OpenCode**: Groq and Ollama worker harness
- **DBOS**: durable workflows, recovery, queues/concurrency
- **Bebop**: decomposition, classification, routing, verification, escalation

## Current vertical slice

```text
TaskCapsule
   -> classify
   -> route
   -> resolve AO project
   -> durable DBOS workflow
   -> spawn/recover AO worker
   -> observe AO session
   -> inspect AO workspace changes
   -> enforce protected-path policy
   -> open AO session-scoped shell
   -> run acceptance commands in the AO worktree
   -> capture exit code + output
   -> PASS or send failure evidence back to the same worker
   -> re-observe + re-verify once
   -> verified / needs_escalation
```

Bebop discovers the running AO daemon through `~/.ao/running.json` unless `AO_BASE_URL` is set.

For OpenCode routes, set:

```env
BEBOP_OLLAMA_MODEL=ollama/<exact-model-id>
BEBOP_GROQ_MODEL=groq/<exact-model-id>
```

On Windows, acceptance verification defaults to PowerShell. Override it with:

```env
BEBOP_VERIFY_SHELL=pwsh
```

## Example task

```json
{
  "id": "T001",
  "title": "Implement parser",
  "objective": "Implement the parser without changing tests.",
  "project": "CourseAI",
  "relevant_files": ["src/parser.py"],
  "protected_paths": ["tests/**"],
  "acceptance_commands": ["pytest tests/test_parser.py"]
}
```

`project` may be an AO project ID, exact project name, or registered project path.

Run:

```powershell
pip install -e ".[dev]"
bebop projects
bebop run task.json
```

## Verification model

Verification is independent of the coding worker.

Bebop:

1. reads changed-file facts from AO,
2. rejects protected-path changes,
3. asks AO to open a shell scoped to the worker session,
4. drives that shell through AO's existing `/mux` WebSocket,
5. runs the task's acceptance commands in the worker's AO-managed worktree,
6. records exit codes and bounded command output.

A worker saying "done" is never enough.

When verification fails and the worker is safely idle/waiting, Bebop sends the concrete failure evidence back to the same worker and allows one repair cycle. If the second verification still fails, the task becomes `needs_escalation`.

Agent Orchestrator must already be installed/running with the target project registered.

## CI

The branch includes GitHub Actions CI that installs the package and runs the test suite.
