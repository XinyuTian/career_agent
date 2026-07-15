from __future__ import annotations

from fastapi.testclient import TestClient

import career_agent.ui.app as ui_app
from career_agent.ui.app import _parse_bool, create_app
from career_agent.repository import CareerRepository
from career_agent.models import (
    Contribution,
    Experience,
    Project,
    Result,
    SkillEvidence,
    Story,
)


def make_client(tmp_path, monkeypatch):
    db = tmp_path / "career.db"
    monkeypatch.setattr(ui_app, "DB_PATH", db)
    return TestClient(create_app(db_path=db)), db


def test_workspace_shell_renders_three_panels(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b'id="tree-panel"' in r.content
    assert b'id="center-panel"' in r.content
    assert b'id="right-panel"' in r.content
    assert b"Select a project" in r.content
    assert b"Paste notes" in r.content


def test_home_lists_experiences(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))

    r = client.get("/")
    assert r.status_code == 200
    assert b"Career navigator" in r.content
    assert b"Search experiences and projects" in r.content
    assert b"Acme" in r.content
    assert b"SWE" in r.content


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

    home = client.get("/")
    assert home.status_code == 200
    assert b"Acme" in home.content

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


def test_project_tabs_show_leaf_sections(tmp_path, monkeypatch):
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

    for tab, needle in (
        ("contributions", b"Built ranking model"),
        ("results", b"CTR"),
        ("skills", b"Python"),
        ("stories", b"Latency spike"),
    ):
        r = client.get(f"/partials/projects/p1?tab={tab}")
        assert r.status_code == 200
        assert b"Search" in r.content
        assert needle in r.content


def test_project_partial_404_for_missing_project(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/partials/projects/does-not-exist?tab=overview")
    assert r.status_code == 404


def test_right_panel_notes_import(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))

    class FakeAgent:
        def __init__(self, *a, **k):
            pass

        def extract_from_notes(self, notes, project_id=None, experience_id=None):
            assert project_id == "p1"
            return {"created": {"contributions": 1}, "updated": {}, "conflicts": []}

    monkeypatch.setattr(ui_app, "build_agent", lambda repo: FakeAgent())
    r = client.post(
        "/projects/p1/notes",
        data={"notes": "I led the ad blindness study."},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert b"Import complete" in r.content or b"created" in r.content.lower()


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


def test_add_experience_from_workspace(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    r = client.post(
        "/experiences",
        data={"organization": "Google", "title": "SWE", "start_date": "2021"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert b"Google" in r.content
    assert b"Select a project" not in r.content
    assert len(CareerRepository(db).list_experiences()) == 1


def test_add_project_beside_experience(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    r = client.post(
        "/experiences/e1/projects",
        data={"project_name": "LTRPM Measurement"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert b"LTRPM Measurement" in r.content
    assert b"Select a project" not in r.content
    assert CareerRepository(db).list_projects("e1")[0].project_name == "LTRPM Measurement"


def test_overview_read_and_save(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness", problem=None))
    r = client.get("/partials/projects/p1?tab=overview")
    assert r.status_code == 200
    assert b"Ad Blindness" in r.content
    assert b"Not set yet" in r.content or b"Problem" in r.content
    edit = client.get("/partials/projects/p1/edit?tab=overview")
    assert edit.status_code == 200
    assert b'name="problem"' in edit.content
    saved = client.post(
        "/partials/projects/p1?tab=overview",
        data={
            "problem": "Users ignore ads",
            "business_context": "Revenue",
            "personal_role": "Lead",
            "users_or_stakeholders": "PMs",
            "responsibilities": "Design study\nAnalyze results",
            "project_stage": "shipped",
            "timeline": "2022",
            "status": "done",
        },
    )
    assert saved.status_code == 200
    project = CareerRepository(db).get_project("p1")
    assert project.problem == "Users ignore ads"
    assert project.responsibilities == ["Design study", "Analyze results"]


def test_contributions_tab_save_create(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Incident Analysis"))
    r = client.post(
        "/partials/projects/p1?tab=contributions",
        data={
            "id": [""],
            "action": ["Wrote postmortem"],
            "technical_method": ["Log analysis"],
            "decision_made": [""],
            "difficulty": [""],
            "alternative_considered": [""],
            "collaborators": [""],
            "ownership_level": ["owner"],
        },
    )
    assert r.status_code == 200
    rows = CareerRepository(db).list_contributions("p1")
    assert len(rows) == 1
    assert rows[0].action == "Wrote postmortem"


def test_contributions_tab_save_update_and_delete(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Incident Analysis"))
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Drafted report", ownership_level="owner")
    )
    repo.create_contribution(
        Contribution(id="c2", project_id="p1", action="Remove me", ownership_level="contributor")
    )
    r = client.post(
        "/partials/projects/p1?tab=contributions",
        data={
            "id": ["c1", "c2"],
            "action": ["Updated report", "Remove me"],
            "technical_method": ["", ""],
            "decision_made": ["", ""],
            "difficulty": ["", ""],
            "alternative_considered": ["", ""],
            "collaborators": ["", ""],
            "ownership_level": ["lead", "contributor"],
            "delete_ids": ["c2"],
        },
    )
    assert r.status_code == 200
    rows = CareerRepository(db).list_contributions("p1")
    assert len(rows) == 1
    assert rows[0].id == "c1"
    assert rows[0].action == "Updated report"
    assert rows[0].ownership_level == "lead"


def test_contributions_tab_read_and_edit(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Incident Analysis"))
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Wrote postmortem", technical_method="Log analysis")
    )
    read = client.get("/partials/projects/p1?tab=contributions")
    assert read.status_code == 200
    assert b"Wrote postmortem" in read.content
    assert b"Log analysis" in read.content
    edit = client.get("/partials/projects/p1/edit?tab=contributions")
    assert edit.status_code == 200
    assert b'name="action"' in edit.content
    assert b"Wrote postmortem" in edit.content


def test_parse_bool():
    assert _parse_bool("") is None
    assert _parse_bool("false") is False
    assert _parse_bool("true") is True


def test_skill_evidence_independently_used_false_round_trips(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Incident Analysis"))
    repo.create_skill_evidence(
        SkillEvidence(id="s1", project_id="p1", skill="Python", independently_used=False)
    )

    edit = client.get("/partials/projects/p1/edit?tab=skills")
    assert edit.status_code == 200
    assert b'value="false" selected' in edit.content

    r = client.post(
        "/partials/projects/p1?tab=skills",
        data={
            "id": ["s1"],
            "skill": ["Python"],
            "proficiency": [""],
            "evidence": [""],
            "recency": [""],
            "frequency": [""],
            "independently_used": ["false"],
        },
    )
    assert r.status_code == 200
    assert repo.get_skill_evidence("s1").independently_used is False


def test_result_is_estimate_false_round_trips(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Incident Analysis"))
    repo.create_result(Result(id="r1", project_id="p1", metric_name="Latency", is_estimate=False))

    edit = client.get("/partials/projects/p1/edit?tab=results")
    assert edit.status_code == 200
    assert b'value="false" selected' in edit.content

    r = client.post(
        "/partials/projects/p1?tab=results",
        data={
            "id": ["r1"],
            "result_type": [""],
            "metric_name": ["Latency"],
            "baseline": [""],
            "final_value": [""],
            "absolute_change": [""],
            "relative_change": [""],
            "business_impact": [""],
            "confidence_level": [""],
            "measurement_method": [""],
            "is_estimate": ["false"],
        },
    )
    assert r.status_code == 200
    assert repo.get_result("r1").is_estimate is False


def test_skills_tab_save_create(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Incident Analysis"))
    r = client.post(
        "/partials/projects/p1?tab=skills",
        data={
            "id": [""],
            "skill": ["Python"],
            "proficiency": ["expert"],
            "evidence": ["Built pipeline"],
            "recency": [""],
            "frequency": [""],
            "independently_used": [""],
        },
    )
    assert r.status_code == 200
    rows = CareerRepository(db).list_skill_evidence("p1")
    assert len(rows) == 1
    assert rows[0].skill == "Python"

