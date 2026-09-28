from bebop.models import PlanDraft, PlannedTask
from bebop.planner import materialize_plan
from bebop.repo_context import goal_search_pattern


def test_materialize_plan_forces_project_and_stable_goal_id():
    draft = PlanDraft(
        tasks=[
            PlannedTask(
                id="T001",
                title="Implement parser",
                objective="Implement transcript parser",
                relevant_files=["src/parser.py"],
                allowed_paths=["src/**"],
            ),
            PlannedTask(
                id="T002",
                title="Verify integration",
                objective="Wire parser into importer",
                dependencies=["T001"],
            ),
        ]
    )

    first = materialize_plan("Finish transcript pipeline", "courseai", draft)
    second = materialize_plan("Finish transcript pipeline", "courseai", draft)

    assert first.id == second.id
    assert first.tasks[0].project == "courseai"
    assert first.tasks[1].dependencies == ["T001"]


def test_goal_search_pattern_removes_generic_words():
    pattern = goal_search_pattern(
        "Finish the CourseAI transcript pipeline and improve course detection"
    )

    assert "Finish" not in pattern
    assert "transcript" in pattern
    assert "pipeline" in pattern
    assert "course" in pattern
