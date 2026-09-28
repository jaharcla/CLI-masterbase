# Bebop Code Hub

Bebop is a thin intelligence, routing, verification, and escalation layer built around existing coding-agent infrastructure.

It does **not** reimplement worktrees, agent process supervision, durable workflow state, repository indexing, or coding-agent harnesses.

## Stack

- **Agent Orchestrator (AO)** — agents, sessions, worktrees, Windows runtime, session shells, durable provider switching
- **OpenCode** — Groq and Ollama worker harness
- **DBOS** — durable workflows, queues, recovery, concurrency
- **PydanticAI** — typed natural-language goal planning
- **grep-ast** — AST-aware repository context
- **pathspec** — gitignore-compatible write/protected path policy
- **stdlib graphlib** — dependency DAG readiness
- **Bebop** — task contracts, classification, routing, verification policy, repair/escalation, goal integration

## End-to-end goal flow

```text
User goal
   ↓
grep-ast repository context
   ↓
PydanticAI → validated GoalPlan
   ↓
graphlib.TopologicalSorter
   ↓
DBOS dependency-safe parallel waves
   ↓
Bebop classifier/router
   ├─ Mechanical/Routine → OpenCode/Ollama
   ├─ Engineering        → OpenCode/Groq
   └─ Reasoning/Critical → Codex
   ↓
AO-managed worker worktree
   ↓
pathspec write/protected-path policy
   ↓
explicit acceptance commands
       or
auto-discovered repo-native verifier
   ↓
objective AO-shell verification
   ↓
FAIL → same-worker repair once
   ↓
FAIL → AO-native in-place switch to Codex
   ↓
objective re-verification
   ↓
canonical verified task commit
   ↓
verified commits inherited by dependent tasks
   ↓
final AO integration worktree
   ↓
repo-wide verification
   ↓
GoalOutcome
```

Workers never decide whether their own task succeeded.

## Natural-language usage

List AO projects:

```powershell
bebop projects
```

Preview the generated plan:

```powershell
bebop plan "Finish the CourseAI transcript pipeline" --project CourseAI
```

Save the plan:

```powershell
bebop plan "Finish the CourseAI transcript pipeline" --project CourseAI -o plan.json
```

Execute a saved plan:

```powershell
bebop run-plan plan.json
```

Or plan and execute in one command:

```powershell
bebop goal "Finish the CourseAI transcript pipeline" --project CourseAI
```

Single-task JSON execution remains available through `bebop run task.json`.

## Planning

The planner uses PydanticAI structured output rather than parsing free-form model prose. It produces a validated DAG of bounded tasks containing:

- dependencies
- relevant files
- allowed write patterns
- protected path patterns
- optional task-specific acceptance commands

Repository context comes from grep-ast rather than a Bebop-specific AST/vector index.

The planner model is configurable:

```env
BEBOP_PLANNER_MODEL=groq:llama-3.3-70b-versatile
GROQ_API_KEY=<key>
```

## Routing

Initial policy:

```text
Mechanical / Routine → OpenCode + Ollama
Engineering          → OpenCode + Groq
Reasoning / Critical → Codex
```

For OpenCode routes set the exact model identifiers OpenCode accepts:

```env
BEBOP_OLLAMA_MODEL=ollama/<exact-model-id>
BEBOP_GROQ_MODEL=groq/<exact-model-id>
```

## Verification

Verification is independent of the coding worker.

Bebop uses AO's session-scoped shell and terminal mux to run checks inside the worker's actual AO worktree and captures an explicit command exit code.

Explicit `acceptance_commands` take priority. If absent, Bebop currently discovers standard repo-native checks such as:

- `pytest -q`
- `ruff check .`
- `go test ./...`
- `cargo test --quiet`
- npm test/lint/build scripts
- `dotnet test`

If Bebop cannot discover objective verification, it does **not** silently accept the task.

## Path policy

`protected_paths` and `allowed_paths` use gitignore-style matching through pathspec.

Example:

```json
{
  "allowed_paths": ["src/**"],
  "protected_paths": ["tests/**/*.py", ".github/**"]
}
```

AO's workspace model distinguishes inherited dependency commits from edits/commits made by the current worker, so a downstream task is evaluated against its own delta rather than blamed for verified predecessor code.

## Repair and escalation

A failed worker gets one repair attempt with the actual machine evidence.

If an OpenCode-backed worker still fails, Bebop uses AO's durable `switch-agent` saga to hand the **same logical session and worktree** to Codex. The new controller receives the failure evidence and Bebop verifies again afterward.

Bebop does not fake an in-place Ollama→Groq swap because AO's current public switch-target surface operates at the harness level.

## Dependency handoff

Each verified graph task is normalized into one canonical Bebop Git commit relative to the exact dependency baseline it received.

Dependent workers:

1. start in their own AO-managed worktree,
2. inherit verified prerequisite commits,
3. receive their task only after inheritance succeeds,
4. are verified independently,
5. produce their own canonical verified commit.

This keeps AO in charge of worktree lifecycle while giving Bebop deterministic dependency inheritance.

## Final goal integration

When all graph tasks verify, Bebop creates a final AO-owned integration workspace, applies the canonical verified task commits in dependency-safe wave order, and runs repo-wide auto-discovered verification.

The final `GoalOutcome` reports:

- each task outcome,
- dependency waves,
- blocked/error tasks,
- integration AO session,
- integration commit SHA,
- integration verification evidence.

Bebop does not modify the user's checked-out branch as part of this flow.

## Configuration

Bebop discovers AO from `~/.ao/running.json` unless `AO_BASE_URL` is provided.

On Windows, acceptance verification defaults to PowerShell. Override with:

```env
BEBOP_VERIFY_SHELL=pwsh
```

DBOS defaults to its local system database configuration; `DBOS_SYSTEM_DATABASE_URL` can override it.

Task queue concurrency defaults to 3 and can be changed with:

```env
BEBOP_TASK_CONCURRENCY=3
```

## CI

GitHub Actions installs the package and runs the test suite on pushes and pull requests.
