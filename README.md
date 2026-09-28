# Bebop Code Hub

Bebop is a thin routing, verification, and escalation layer for existing coding-agent infrastructure.

It does **not** reimplement worktrees, agent process supervision, durable session state, or coding-agent harnesses.

## Stack

- **Agent Orchestrator**: workers, sessions, worktrees, Codex/Copilot/OpenCode execution, durable provider switching
- **OpenCode**: Groq and Ollama worker harness
- **DBOS**: durable workflows, recovery, queues/concurrency
- **Bebop**: decomposition, classification, routing, verification, repair policy, escalation

## Current execution ladder

```text
TaskCapsule
   -> classify
   -> initial route

Mechanical/Routine
   -> OpenCode / Ollama

Engineering
   -> OpenCode / Groq

Reasoning/Critical
   -> Codex

worker finishes
   -> inspect AO workspace
   -> reject protected-path changes
   -> run acceptance commands in AO session worktree
   -> PASS => verified
   -> FAIL => send concrete evidence to same worker once
   -> re-verify
   -> PASS => verified_after_repair
   -> FAIL + current worker is OpenCode
        -> AO durable switch-agent: same session/worktree -> Codex
        -> send latest verification evidence
        -> Codex repairs
        -> re-verify
        -> PASS => verified_after_escalation
        -> FAIL => escalated_worker_failed
   -> FAIL + current worker already Codex
        -> strong_worker_failed
```

The escalation step uses AO's own durable agent-switch saga, so Bebop does **not** create a second worktree or manually merge an escalation branch.

## AO discovery

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

## Escalation model

The first failure goes back to the same worker with exact machine evidence.

If the same worker fails verification again:

- OpenCode-backed work escalates in-place to **Codex** through `POST /api/v1/sessions/{sessionId}/switch-agent`.
- Bebop uses a deterministic idempotency key so a DBOS replay resolves to the same switch saga instead of creating a duplicate provider handoff.
- The AO session ID and worktree remain unchanged.
- The new Codex controller receives the latest verification evidence and works on the existing files.
- Bebop independently verifies the result again.

AO's current public in-place switch target surface exposes Codex/Claude/fx, not a second model behind the same OpenCode harness. Because of that, Bebop does not pretend it can perform an in-place Ollama -> Groq provider swap on an existing OpenCode session.

Agent Orchestrator must already be installed/running with the target project registered.

## CI

GitHub Actions installs the package and runs the test suite for pushes and pull requests.
