from dataclasses import replace

import pytest

from career_agent.models import (
    Contribution,
    Experience,
    OpenQuestion,
    Project,
    Result,
    SkillEvidence,
    Story,
)
from career_agent.repository import CareerRepository


def make_repository(tmp_path):
    repo = CareerRepository(tmp_path / "career.db")
    repo.create_experience(
        Experience(
            id="e1",
            organization="Acme",
            title="SWE",
            start_date="2020-01",
            business_context="Cloud infrastructure",
        )
    )
    repo.create_project(
        Project(
            id="p1",
            experience_id="e1",
            project_name="Platform",
            responsibilities=["design", "delivery"],
        )
    )
    return repo


def test_experience_and_project_crud_and_unique_finders(tmp_path):
    repo = make_repository(tmp_path)

    experience = repo.get_experience("e1")
    assert experience is not None
    assert experience.organization == "Acme"
    assert repo.find_experience_by_key("Acme", "SWE", "2020-01") == experience
    assert repo.find_experience_by_key("Other", "SWE", "2020-01") is None
    repo.update_experience(replace(experience, team="Infrastructure"))
    assert repo.list_experiences()[0].team == "Infrastructure"

    project = repo.get_project("p1")
    assert project is not None
    assert project.responsibilities == ["design", "delivery"]
    assert repo.find_project_by_key("e1", "Platform") == project
    assert repo.find_project_by_key("e1", "Missing") is None
    repo.update_project(replace(project, status="shipped"))
    assert repo.list_projects("e1")[0].status == "shipped"
    assert repo.list_projects("missing") == []


def test_leaf_crud_and_skill_finder(tmp_path):
    repo = make_repository(tmp_path)
    contribution = Contribution(
        id="c1",
        project_id="p1",
        action="Built deployment automation",
        collaborators=["A", "B"],
    )
    result = Result(
        id="r1",
        project_id="p1",
        metric_name="Latency",
        final_value="100ms",
        is_estimate=True,
    )
    skill = SkillEvidence(
        id="sk1",
        project_id="p1",
        skill="Python",
        evidence="Built automation",
        independently_used=True,
    )
    story = Story(
        id="s1",
        project_id="p1",
        competency="Leadership",
        situation="A delayed launch",
    )

    repo.create_contribution(contribution)
    repo.create_result(result)
    repo.create_skill_evidence(skill)
    repo.create_story(story)

    assert repo.get_contribution("c1") == contribution
    assert repo.get_result("r1") == result
    assert repo.get_skill_evidence("sk1") == skill
    assert repo.get_story("s1") == story
    assert repo.list_contributions("p1") == [contribution]
    assert repo.list_results("p1") == [result]
    assert repo.list_skill_evidence("p1") == [skill]
    assert repo.list_stories("p1") == [story]
    assert repo.find_skill_evidence("p1", "Python") == skill
    assert repo.find_skill_evidence("p1", "Rust") is None

    repo.update_contribution(replace(contribution, ownership_level="lead"))
    repo.update_result(replace(result, business_impact="Faster pages"))
    repo.update_skill_evidence(replace(skill, proficiency="advanced"))
    repo.update_story(replace(story, lesson="Escalate earlier"))

    assert repo.get_contribution("c1").ownership_level == "lead"
    assert repo.get_result("r1").business_impact == "Faster pages"
    assert repo.get_skill_evidence("sk1").proficiency == "advanced"
    assert repo.get_story("s1").lesson == "Escalate earlier"


def test_open_questions_graph_summary_and_counts(tmp_path):
    repo = make_repository(tmp_path)
    repo.create_project(Project(id="p2", experience_id="e1", project_name="API"))
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Built deployment automation")
    )
    repo.create_open_question(
        OpenQuestion(
            id="q1",
            related_entity_type="project",
            related_entity_id="p1",
            question="What was the adoption?",
        )
    )
    repo.create_open_question(
        OpenQuestion(
            id="q2",
            related_entity_type="project",
            related_entity_id="p1",
            question="Resolved",
            status="closed",
        )
    )

    assert [question.id for question in repo.list_open_questions()] == ["q1"]
    assert [question.id for question in repo.list_open_questions("closed")] == ["q2"]
    assert [question.id for question in repo.list_open_questions(None)] == ["q1", "q2"]

    all_summary = repo.graph_summary()
    assert all_summary["experiences"][0]["id"] == "e1"
    assert "created_at" not in all_summary["experiences"][0]
    assert "employment_type" not in all_summary["experiences"][0]
    assert {project["id"] for project in all_summary["projects"]} == {"p1", "p2"}
    assert all_summary["contributions"][0]["id"] == "c1"
    project_summary = repo.graph_summary(project_id="p1")
    assert [project["id"] for project in project_summary["projects"]] == ["p1"]
    assert project_summary["experiences"][0]["id"] == "e1"
    experience_summary = repo.graph_summary(experience_id="missing")
    assert all(not rows for rows in experience_summary.values())

    assert repo.counts() == {
        "experiences": 1,
        "projects": 2,
        "contributions": 1,
        "results": 0,
        "skill_evidence": 0,
        "stories": 0,
        "open_questions": 2,
        "embeddings": 0,
    }


def test_embedding_upsert_search_delete_and_unembedded_leaves(tmp_path):
    repo = make_repository(tmp_path)
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Built CI pipeline")
    )
    repo.create_result(
        Result(id="r1", project_id="p1", business_impact="Reduced incidents")
    )

    assert repo.list_unembedded_leaves() == [
        ("contribution", "c1"),
        ("result", "r1"),
    ]

    repo.upsert_embedding("contribution", "c1", [1.0, 0.0])
    repo.upsert_embedding("result", "r1", [0.0, 1.0])
    repo.upsert_embedding("contribution", "c1", [0.9, 0.1])

    matches = repo.search_leaves([1.0, 0.0], limit=2)
    assert [match[:2] for match in matches] == [
        ("contribution", "c1"),
        ("result", "r1"),
    ]
    assert matches[0][2] > matches[1][2]
    assert repo.list_unembedded_leaves() == []

    repo.delete_embedding("contribution", "c1")
    assert repo.list_unembedded_leaves() == [("contribution", "c1")]


def test_searchable_text_and_leaf_with_parents(tmp_path):
    repo = make_repository(tmp_path)
    repo.create_contribution(
        Contribution(
            id="c1",
            project_id="p1",
            action="Built CI pipeline",
            technical_method="GitHub Actions",
        )
    )

    text = repo.leaf_searchable_text("contribution", "c1")
    assert text == "\n".join(
        [
            "Built CI pipeline",
            "GitHub Actions",
            "Platform",
            "Acme",
            "SWE",
        ]
    )

    item = repo.get_leaf_with_parents("contribution", "c1")
    assert item["leaf"]["id"] == "c1"
    assert item["project"]["id"] == "p1"
    assert item["experience"]["id"] == "e1"
    assert item["entity_type"] == "contribution"
    assert item["entity_id"] == "c1"


def test_writes_respect_caller_managed_transaction(tmp_path):
    repo = make_repository(tmp_path)

    repo.conn.execute("BEGIN")
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Temporary write")
    )
    repo.conn.rollback()

    assert repo.get_contribution("c1") is None


def test_embedding_upsert_rejects_unknown_leaf(tmp_path):
    repo = make_repository(tmp_path)

    with pytest.raises(KeyError, match="contribution not found"):
        repo.upsert_embedding("contribution", "missing", [1.0, 0.0])


def test_graph_summary_rejects_conflicting_scopes(tmp_path):
    repo = make_repository(tmp_path)
    repo.create_experience(Experience(id="e2", organization="Beta", title="SWE"))

    summary = repo.graph_summary(experience_id="e2", project_id="p1")

    assert all(not rows for rows in summary.values())


def test_delete_contribution(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE", start_date="2020"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Platform"))
    repo.create_contribution(Contribution(id="c1", project_id="p1", action="Built CI"))
    assert repo.delete_contribution("c1") is True
    assert repo.list_contributions("p1") == []
    assert repo.delete_contribution("c1") is False


def test_delete_contribution_cleans_embedding(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE", start_date="2020"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Platform"))
    repo.create_contribution(Contribution(id="c1", project_id="p1", action="Built CI"))
    repo.upsert_embedding("contribution", "c1", [1.0, 0.0])
    assert repo.counts()["embeddings"] == 1

    assert repo.delete_contribution("c1") is True
    assert repo.counts()["embeddings"] == 0


def test_dismiss_gap_roundtrip(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE", start_date="2020"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="P"))
    repo.dismiss_gap("p1", "overview.problem")
    assert "overview.problem" in repo.list_dismissed_gap_keys("p1")
    repo.dismiss_gap("p1", "overview.problem")  # idempotent
    assert repo.list_dismissed_gap_keys("p1") == {"overview.problem"}


def test_update_open_question_status(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE", start_date="2020"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="P"))
    q = OpenQuestion(id="q1", related_entity_type="project", related_entity_id="p1", question="Metric?")
    repo.create_open_question(q)
    q.status = "dismissed"
    repo.update_open_question(q)
    assert repo.list_open_questions(status="dismissed")[0].id == "q1"


def test_duplicate_project_deep_copies_all_leaves(tmp_path):
    repo = make_repository(tmp_path)
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Built pipeline",
                     collaborators=["Ada", "Grace"])
    )
    repo.create_result(
        Result(id="r1", project_id="p1", metric_name="latency", is_estimate=True)
    )
    repo.create_skill_evidence(
        SkillEvidence(id="s1", project_id="p1", skill="Python", independently_used=True)
    )
    repo.create_story(Story(id="st1", project_id="p1", competency="Ownership"))

    copy = repo.duplicate_project("p1")

    assert copy is not None
    assert copy.id != "p1"
    assert copy.project_name == "Platform (copy)"
    assert copy.experience_id == "e1"
    assert copy.status is None
    assert copy.responsibilities == ["design", "delivery"]

    # Original is untouched
    assert len(repo.list_projects("e1")) == 2
    assert len(repo.list_contributions("p1")) == 1

    # Copies exist with new ids pointing at the new project
    copied_contributions = repo.list_contributions(copy.id)
    assert len(copied_contributions) == 1
    assert copied_contributions[0].id != "c1"
    assert copied_contributions[0].action == "Built pipeline"
    assert copied_contributions[0].collaborators == ["Ada", "Grace"]
    assert len(repo.list_results(copy.id)) == 1
    assert repo.list_results(copy.id)[0].is_estimate is True
    assert len(repo.list_skill_evidence(copy.id)) == 1
    assert repo.list_skill_evidence(copy.id)[0].independently_used is True
    assert len(repo.list_stories(copy.id)) == 1


def test_duplicate_project_missing_returns_none(tmp_path):
    repo = make_repository(tmp_path)
    assert repo.duplicate_project("does-not-exist") is None


def test_duplicate_project_disambiguates_repeated_copies(tmp_path):
    repo = make_repository(tmp_path)
    first = repo.duplicate_project("p1")
    second = repo.duplicate_project("p1")
    assert first is not None and second is not None
    names = {p.project_name for p in repo.list_projects("e1")}
    assert names == {"Platform", "Platform (copy)", "Platform (copy 2)"}
