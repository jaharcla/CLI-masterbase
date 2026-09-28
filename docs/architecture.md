# Bebop Architecture

## Ownership boundary

Bebop owns the correctness-critical control plane:

- task decomposition
- dependency graph
- task classification
- routing
- persistent task state
- verification
- retry and escalation
- merge policy
- project memory

External coding agents are bounded workers. They do not decide whether their own task succeeded.

## Initial execution model

1. A goal is decomposed into tasks.
2. Tasks are persisted in SQLite.
3. The DAG scheduler marks dependency-safe tasks ready.
4. A task receives an isolated git worktree.
5. A worker executes a bounded task capsule.
6. Bebop runs acceptance checks independently.
7. Passing work can be integrated.
8. Failures produce evidence for retry or escalation.

## Replaceable execution layer

The native backend is mandatory.

Future optional backends may wrap external orchestrators such as Agent Orchestrator or Ordewell, but the Bebop planner, router, task state, and verifier must remain independent of them.

## MVP worker targets

- OpenCode + Ollama for mechanical/routine work
- OpenCode + Groq for engineering work
- Codex CLI for reasoning and critical review
- Local subprocesses for verification
