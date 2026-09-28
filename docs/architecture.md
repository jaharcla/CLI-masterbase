# Bebop OSS-first architecture

Bebop is intentionally a thin intelligence/control layer. Infrastructure already solved by maintained open-source projects stays outside Bebop.

## Reused infrastructure

### Agent Orchestrator

AO owns:

- coding-agent process/session lifecycle
- Codex/Copilot/OpenCode adapters
- Git worktrees and branches
- persistent session state
- Windows runtime support
- session HTTP API
- session-scoped shells and terminal mux
- workspace diff/read models
- durable provider switching

Bebop does not recreate these capabilities.

### OpenCode

OpenCode is the shared coding harness for API/local routes such as Groq and Ollama.

### DBOS

DBOS owns:

- durable workflows
- workflow replay/recovery
- queue execution
- concurrency limits
- child workflow persistence

Bebop does not own a scheduler database or process queue.

### PydanticAI

PydanticAI owns structured LLM interaction for natural-language goal planning. Bebop provides the Pydantic plan schema and planning policy.

### grep-ast

grep-ast supplies AST-aware repository context. Bebop does not build a private AST/vector search stack for the MVP.

### pathspec

pathspec supplies Git-compatible matching for allowed/protected write scopes.

### Python graphlib

`TopologicalSorter` owns DAG readiness/cycle semantics. Bebop only maps validated task dependencies into it.

## Bebop-owned intelligence

Bebop owns:

1. goal/task contracts
2. planning policy
3. complexity/risk classification
4. capability/cost routing
5. context/task-capsule assembly
6. write-scope policy
7. objective verification policy
8. repair policy
9. escalation policy
10. verified dependency handoff
11. goal integration policy
12. usage/performance learning later

## Full execution path

```text
natural-language goal
  ↓
grep-ast repo context
  ↓
PydanticAI PlanDraft
  ↓
validated GoalPlan
  ↓
TopologicalSorter
  ↓
DBOS queue: ready tasks in parallel
  ↓
Bebop classify + route
  ↓
AO worktree/session
  ↓
OpenCode/Ollama | OpenCode/Groq | Codex
  ↓
AO workspace facts
  ↓
pathspec policy
  ↓
explicit or auto-discovered machine verification
  ↓
same-worker repair if needed
  ↓
AO-native Codex escalation if needed
  ↓
canonical verified task commit
  ↓
dependency commit inheritance
  ↓
next DAG wave
  ↓
final AO integration worktree
  ↓
repo-wide verification
```

## Dependency correctness

Every graph task begins from a captured dependency baseline.

Bebop may inherit verified predecessor commits into the new AO worktree, but AO still owns the worktree itself. When the task verifies, Bebop soft-resets to the captured dependency baseline and produces one canonical verified commit containing exactly that task's accepted delta. This also normalizes agents that created their own intermediate commits.

Downstream tasks inherit the complete transitive verified lineage.

AO workspace policy checks ignore only known inherited commit SHAs. New commits made by the current worker remain visible to protected/allowed-path verification.

## Failure propagation

A failed task is never marked complete in the TopologicalSorter, so dependent nodes do not unlock. Independent graph branches can still complete.

A graph may therefore end with:

- verified tasks,
- failed tasks,
- blocked descendants,
- independent successful branches.

## Verification

A worker's self-report is not correctness evidence.

Verification combines:

- AO changed-file/commit facts
- pathspec allowed/protected scopes
- task-specific acceptance commands when supplied
- automatic repo-native verifier discovery otherwise
- AO session-scoped shell exit codes/output

No objective verifier means no automatic success.

## Repair and premium escalation

One failed verification is returned to the same worker with exact evidence.

A second failed OpenCode attempt can trigger AO's durable `switch-agent` saga to Codex. The logical session/worktree remains the same and the switch uses an idempotency key.

## Goal integration

After every required task succeeds, Bebop creates a separate AO-managed integration session, applies canonical verified task commits in dependency-safe order, and runs repository-wide verification.

The integration result is returned as part of `GoalOutcome`; the user's active branch is not silently modified.

## Architectural boundary

If AO disappeared, Bebop would lose execution/worktree infrastructure but retain its planner, routing policy, graph semantics, verification policy, and task/goal contracts.

If DBOS disappeared, Bebop would lose durable scheduling but retain its task graph and execution intelligence.

If PydanticAI or grep-ast disappeared, the execution engine could still consume a manually supplied `GoalPlan`.

Those boundaries are intentional: Bebop owns its differentiating decisions, not commodity infrastructure.
