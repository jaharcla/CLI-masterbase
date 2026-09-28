from __future__ import annotations

import hashlib
import os

from pydantic_ai import Agent

from bebop.models import GoalPlan, PlanDraft, TaskCapsule


PLANNER_INSTRUCTIONS = """
You are Bebop's software-engineering planner.

Convert one user goal into the smallest useful dependency graph of bounded coding
tasks. The executor, worktrees, verification, retries, and escalation are handled
elsewhere.

Rules:
- Use stable task IDs like T001, T002, T003.
- Dependencies must reference only task IDs in this plan.
- Keep tasks independently executable where possible.
- Put genuinely independent tasks in parallel by omitting unnecessary dependencies.
- relevant_files must contain only paths supported by the supplied repository context.
  If context is insufficient, leave the list conservative rather than inventing paths.
- allowed_paths should tightly bound implementation writes using gitignore-style patterns.
- protected_paths should protect tests/CI/verifier artifacts unless the task explicitly
  exists to author or modify those artifacts.
- acceptance_commands are optional. Add task-specific checks when clearly justified;
  otherwise leave them empty and Bebop's verifier registry will discover repo-native checks.
- Do not assign models or agents. Bebop routes tasks after planning.
- Do not create planning/meta tasks unless repository inspection itself is necessary.
"""


def plan_goal(
    goal: str,
    project: str,
    repo_context: str,
    *,
    model: str | None = None,
) -> GoalPlan:
    model_name = model or os.getenv(
        "BEBOP_PLANNER_MODEL",
        "groq:openai/gpt-oss-120b",
    )

    agent = Agent(
        model_name,
        output_type=PlanDraft,
        instructions=PLANNER_INSTRUCTIONS,
        retries={"output": 2},
    )
    result = agent.run_sync(
        f"PROJECT: {project}\n\n"
        f"USER GOAL:\n{goal}\n\n"
        f"REPOSITORY CONTEXT FROM GREP-AST:\n{repo_context}"
    )
    return materialize_plan(goal, project, result.output)


def materialize_plan(
    goal: str,
    project: str,
    draft: PlanDraft,
) -> GoalPlan:
    digest = hashlib.sha256(
        f"{project}\0{goal}".encode("utf-8")
    ).hexdigest()[:12]
    plan_id = f"goal-{digest}"

    tasks = [
        TaskCapsule(
            id=task.id,
            title=task.title,
            objective=task.objective,
            project=project,
            dependencies=task.dependencies,
            relevant_files=task.relevant_files,
            allowed_paths=task.allowed_paths,
            protected_paths=task.protected_paths,
            acceptance_commands=task.acceptance_commands,
        )
        for task in draft.tasks
    ]

    return GoalPlan(
        id=plan_id,
        goal=goal,
        project=project,
        tasks=tasks,
    )
