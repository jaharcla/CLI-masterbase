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
```

Bebop discovers the running AO daemon through `~/.ao/running.json` unless `AO_BASE_URL` is set.

For OpenCode routes, set:

```env
BEBOP_OLLAMA_MODEL=ollama/<exact-model-id>
BEBOP_GROQ_MODEL=groq/<exact-model-id>
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

## Current verification boundary

Bebop currently verifies **workspace policy** from AO-reported changed files. It deliberately does **not** claim objective success for tasks with acceptance commands yet.

Until a machine-verifiable command execution surface is added, a task with `acceptance_commands` ends in:

```text
awaiting_objective_verification
```

rather than being falsely marked complete.

Agent Orchestrator must already be installed/running with the target project registered.
