# Bebop Code Hub

Bebop is a local-first coding orchestrator that decomposes a development goal into bounded tasks, routes each task to the cheapest capable worker, verifies the result independently, and escalates only when evidence requires stronger reasoning.

## Core principle

> Use expensive intelligence only where it materially improves the outcome; let inexpensive or unlimited workers handle everything else.

## MVP

The first implementation targets:

```text
user goal
  -> task decomposition
  -> dependency DAG
  -> task classification
  -> routing
  -> isolated git worktree
  -> worker execution
  -> objective verification
  -> retry / escalation
  -> integration
```

Initial workers:

- Ollama through OpenCode
- Groq through OpenCode
- Codex CLI for protected reasoning tasks
- Local verification commands

Bebop owns planning, routing, task state, verification, escalation, and merge policy. External orchestrators remain optional execution backends.

## Status

Repository bootstrap in progress.