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
   -> deterministic baseline classifier
   -> routing policy
   -> DBOS durable workflow
   -> POST /api/v1/sessions to Agent Orchestrator
```

The current code intentionally stops before implementing a second process manager or scheduler.

## Example task

```json
{
  "id": "T001",
  "title": "Implement parser",
  "objective": "Implement the parser without changing tests.",
  "project_id": "your-ao-project-id",
  "relevant_files": ["src/parser.py"],
  "protected_paths": ["tests/**"],
  "acceptance_commands": ["pytest tests/test_parser.py"]
}
```

Run with:

```powershell
pip install -e ".[dev]"
bebop run task.json
```

Agent Orchestrator must already be installed/running with the target project registered.
