from career_agent.completeness import evaluate_project_completeness
from career_agent.models import (
    Contribution,
    OpenQuestion,
    Project,
    Result,
    SkillEvidence,
    Story,
)


def test_empty_project_missing_overview_and_coverage():
    project = Project(id="p1", experience_id="e1", project_name="Ad Blindness")
    report = evaluate_project_completeness(
        project=project,
        contributions=[],
        results=[],
        skills=[],
        stories=[],
        open_questions=[],
        dismissed_keys=set(),
    )
    keys = {g.key for g in report.missing}
    assert "overview.problem" in keys
    assert "coverage.contributions" in keys
    assert report.percent < 100


def test_dismissed_key_excluded_from_score():
    project = Project(
        id="p1",
        experience_id="e1",
        project_name="P",
        problem="x",
        business_context="x",
        personal_role="x",
        users_or_stakeholders="x",
    )
    base = evaluate_project_completeness(
        project=project,
        contributions=[],
        results=[],
        skills=[],
        stories=[],
        open_questions=[],
        dismissed_keys=set(),
    )
    dismissed = evaluate_project_completeness(
        project=project,
        contributions=[],
        results=[],
        skills=[],
        stories=[],
        open_questions=[],
        dismissed_keys={"coverage.contributions"},
    )
    assert "coverage.contributions" not in {g.key for g in dismissed.missing}
    assert dismissed.percent >= base.percent


def test_open_question_appears_as_missing():
    project = Project(
        id="p1",
        experience_id="e1",
        project_name="P",
        problem="x",
        business_context="x",
        personal_role="x",
        users_or_stakeholders="x",
    )
    q = OpenQuestion(
        id="q1",
        related_entity_type="project",
        related_entity_id="p1",
        question="What was the latency win?",
    )
    report = evaluate_project_completeness(
        project=project,
        contributions=[
            Contribution(
                id="c1",
                project_id="p1",
                action="Built CI",
                ownership_level="owner",
            )
        ],
        results=[
            Result(
                id="r1",
                project_id="p1",
                metric_name="latency",
                baseline="10",
                final_value="5",
            )
        ],
        skills=[
            SkillEvidence(
                id="s1",
                project_id="p1",
                skill="SQL",
                evidence="wrote queries",
            )
        ],
        stories=[Story(id="t1", project_id="p1", situation="x")],
        open_questions=[q],
        dismissed_keys=set(),
    )
    assert any(g.key == "open_question.q1" for g in report.missing)
