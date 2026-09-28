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
- session-scoped shells
- durable provider switching
- workspace and PR state

Bebop talks to AO through its local HTTP API and terminal mux. It does not recreate AO internals.

### OpenCode

OpenCode is the worker harness for API/local-model routes:

- Groq
- Ollama

AO launches OpenCode as the agent harness; Bebop selects the provider/model route.

### DBOS

DBOS owns durable workflow execution, replay/recovery, and later queue/concurrency control.

Bebop does not implement its own scheduler database.

## Bebop-owned code

Bebop owns only:

1. task decomposition
2. multidimensional classification
3. cost/capability routing
4. task-capsule generation
5. protected-path policy
6. objective acceptance verification
7. repair policy
8. escalation policy
9. worker-performance learning later

## Execution boundary

```text
goal
  -> Bebop planner/classifier/router
  -> DBOS durable workflow
  -> AO session API
  -> Codex | Copilot | OpenCode
                         -> Groq | Ollama
  -> AO workspace facts
  -> AO session-scoped shell
  -> Bebop objective verification
  -> same-worker repair
  -> AO-native switch-agent escalation when required
```

## Escalation

Bebop does not create a second implementation worktree just to escalate reasoning.

For an OpenCode-backed task that fails objective verification twice:

```text
OpenCode worker
  -> verification fail
  -> same-worker repair
  -> verification fail
  -> AO durable switch-agent
  -> same logical session
  -> same worktree
  -> Codex controller
  -> verification evidence injected
  -> objective re-verification
```

The switch request uses AO's idempotency support. DBOS replay therefore reuses the same durable switch request rather than blindly launching a second provider replacement.

AO's current public switch-target contract exposes Codex/Claude/fx. A Groq/Ollama change is a model/provider change inside OpenCode, not an AO-native in-place harness switch, so Bebop does not fake that capability.

## Correctness principle

External agents may propose work, but they never decide whether their own task succeeded.

Bebop accepts work only from independent machine evidence plus policy checks.

If AO disappeared, Bebop would lose execution infrastructure but retain its routing/verification intelligence. That dependency is intentional: reuse infrastructure instead of cloning it.
