# Bebop OSS-first architecture

Bebop is intentionally a thin intelligence layer.

## Reused infrastructure

### Agent Orchestrator
AO owns:
- coding-agent process/session lifecycle
- Codex/Copilot/OpenCode adapters
- git worktrees and branches
- persistent session state
- Windows runtime support
- session HTTP API
- workspace and PR state

Bebop talks to AO through its local HTTP API. It does not recreate AO internals.

### OpenCode
OpenCode is the worker harness for API/local-model routes:
- Groq
- Ollama

AO launches OpenCode as the agent harness; Bebop only selects the route.

### DBOS
DBOS owns durable workflow execution, retries/recovery, and later queue/concurrency control.
Bebop does not implement its own scheduler database.

## Bebop-owned code

Bebop should only own:
1. task decomposition
2. multidimensional classification
3. cost/capability routing
4. task-capsule generation
5. verification policy
6. escalation policy
7. worker-performance learning later

## Boundary

```text
goal
  -> Bebop planner/classifier/router
  -> DBOS durable workflow
  -> AO session API
  -> Codex | Copilot | OpenCode
                         -> Groq | Ollama
  -> AO workspace facts
  -> Bebop verification policy
  -> retry/escalate
```

If AO disappeared, Bebop would lose execution infrastructure, but not its task/routing/verification intelligence. That is intentional: AO is infrastructure we reuse rather than clone.
