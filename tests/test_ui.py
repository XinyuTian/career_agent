from __future__ import annotations

from fastapi.testclient import TestClient

import career_agent.ui.app as ui_app
from career_agent.ui.app import create_app
from career_agent.repository import CareerRepository
from career_agent.models import (
    Contribution,
    Experience,
    OpenQuestion,
    Project,
    Result,
    SkillEvidence,
    Story,
)


def make_client(tmp_path, monkeypatch):
    db = tmp_path / "career.db"
    monkeypatch.setattr(ui_app, "DB_PATH", db)
    return TestClient(create_app(db_path=db)), db


def test_home_lists_experiences(tmp_path, monkeypatch):
    db = tmp_path / "career.db"
    monkeypatch.setattr(ui_app, "DB_PATH", db)
    client = TestClient(create_app(db_path=db))
    r = client.get("/")
    assert r.status_code == 200
    assert b"Experiences" in r.content


def test_create_experience_and_project(tmp_path, monkeypatch):
    db = tmp_path / "career.db"
    client = TestClient(create_app(db_path=db))
    r = client.post(
        "/experiences",
        data={
            "organization": "Acme",
            "title": "SWE",
            "start_date": "2020",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    repo = CareerRepository(db)
    experiences = repo.list_experiences()
    assert len(experiences) == 1
    experience = experiences[0]

    detail = client.get(f"/experiences/{experience.id}")
    assert detail.status_code == 200
    assert b"Acme" in detail.content

    r2 = client.post(
        f"/experiences/{experience.id}/projects",
        data={"project_name": "Search Revamp"},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)

    projects = repo.list_projects(experience.id)
    assert len(projects) == 1
    assert projects[0].project_name == "Search Revamp"


def test_create_experience_rejects_blank_names(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)

    r = client.post(
        "/experiences",
        data={"organization": "   ", "title": "SWE"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert b"Organization and title are required." in r.content
    assert len(CareerRepository(db).list_experiences()) == 0

    r2 = client.post(
        "/experiences",
        data={"organization": "Acme", "title": "\t\n"},
        follow_redirects=False,
    )
    assert r2.status_code == 400
    assert len(CareerRepository(db).list_experiences()) == 0


def test_create_project_rejects_blank_name(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))

    r = client.post(
        "/experiences/e1/projects",
        data={"project_name": "   "},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert b"Project name is required." in r.content
    assert len(repo.list_projects("e1")) == 0


def test_project_detail_shows_leaf_sections(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)

    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Built ranking model")
    )
    repo.create_result(
        Result(id="r1", project_id="p1", metric_name="CTR", final_value="12%")
    )
    repo.create_skill_evidence(
        SkillEvidence(id="s1", project_id="p1", skill="Python", evidence="ML pipeline")
    )
    repo.create_story(
        Story(id="st1", project_id="p1", situation="Latency spike", action="Profiled hot path")
    )

    r = client.get("/projects/p1")
    assert r.status_code == 200
    assert b"Search" in r.content
    for heading in (b"Contributions", b"Results", b"Skill evidence", b"Stories"):
        assert heading in r.content
    assert b"Built ranking model" in r.content
    assert b"CTR" in r.content
    assert b"Python" in r.content
    assert b"Latency spike" in r.content
    assert b"notes" in r.content.lower()


def test_project_detail_404_for_missing_project(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/projects/does-not-exist")
    assert r.status_code == 404


def test_notes_import_uses_agent(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)

    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))

    calls = {}

    class FakeAgent:
        def __init__(self, repo):
            self.repo = repo

        def extract_from_notes(self, notes, *, project_id=None, experience_id=None):
            calls["notes"] = notes
            calls["project_id"] = project_id
            return {"created": {"contributions": 1}, "updated": {}, "conflicts": []}

    monkeypatch.setattr(ui_app, "build_agent", lambda repo: FakeAgent(repo))

    r = client.post(
        "/projects/p1/notes",
        data={"notes": "Shipped a new ranking model."},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert calls["project_id"] == "p1"
    assert calls["notes"] == "Shipped a new ranking model."
    assert b"Import complete" in r.content
    assert b"created 1" in r.content


def test_open_questions_page_lists_questions(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_open_question(
        OpenQuestion(
            id="q1",
            related_entity_type="project",
            related_entity_id="p1",
            question="What was the measured impact?",
        )
    )

    r = client.get("/open-questions")
    assert r.status_code == 200
    assert b"What was the measured impact?" in r.content
