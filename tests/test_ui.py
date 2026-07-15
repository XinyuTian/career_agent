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
    OpenQuestion,
)


def make_client(tmp_path, monkeypatch):
    db = tmp_path / "career.db"
    monkeypatch.setattr(ui_app, "DB_PATH", db)
    return TestClient(create_app(db_path=db)), db


def _compute_default_widths(viewport_width: int, chrome: int = 80) -> tuple[int, int]:
    min_side, min_center = 180, 360
    left_max, right_max = 360, 420
    available = max(viewport_width - chrome, min_side * 2 + min_center)
    left = min(left_max, max(min_side, round(viewport_width * 0.20)))
    right = min(right_max, max(200, round(viewport_width * 0.24)))
    overflow = left + right + min_center - available
    if overflow > 0:
        total = left + right
        left = max(min_side, round(left - (overflow * left) / total))
        right = max(min_side, round(right - (overflow * right) / total))
        while left + right + min_center > available and (left > min_side or right > min_side):
            if left >= right and left > min_side:
                left -= 1
            elif right > min_side:
                right -= 1
            else:
                break
    return left, right


def test_default_width_formula_scales_and_clamps():
    wide_l, wide_r = _compute_default_widths(1600)
    narrow_l, narrow_r = _compute_default_widths(900)
    assert wide_l >= narrow_l or wide_r >= narrow_r
    assert 180 <= narrow_l <= 360
    assert 180 <= narrow_r <= 420
    assert narrow_l + narrow_r + 360 <= 900


def test_workspace_script_has_no_window_resize_recompute(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    html = client.get("/").text
    assert 'addEventListener("resize"' not in html
    assert "addEventListener('resize'" not in html


def test_workspace_shell_includes_design_tokens(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b"--accent:" in r.content
    assert b"--bg-panel:" in r.content
    assert b"Inter" in r.content


def test_workspace_shell_renders_three_panels(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b'id="tree-panel"' in r.content
    assert b'id="center-panel"' in r.content
    assert b'id="right-panel"' in r.content
    assert b"Select a project" in r.content
    assert b"Paste notes" in r.content


def test_workspace_has_column_splitters(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b'class="splitter"' in r.content
    assert b'data-side="left"' in r.content
    assert b'data-side="right"' in r.content
    assert b'role="separator"' in r.content
    assert b'aria-orientation="vertical"' in r.content
    assert b"--left-w" in r.content
    assert b"--right-w" in r.content
    assert b"localStorage" not in r.content
    assert b"sessionStorage" not in r.content


def test_workspace_layout_formula_helper_present(tmp_path, monkeypatch):
    """Shell must expose pure default-width helper for the load-time formula."""
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert b"computeDefaultWidths" in r.content
    assert b"__workspaceLayout" in r.content


def test_home_lists_experiences(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))

    r = client.get("/")
    assert r.status_code == 200
    assert b"Experiences" in r.content
    assert b'placeholder="Search"' in r.content
    assert b"+ Add" in r.content
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


def test_add_project_validation_preserves_selected_project(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))

    r = client.post(
        "/experiences/e1/projects",
        data={"project_name": "   ", "selected_project_id": "p1"},
        follow_redirects=False,
    )

    assert r.status_code == 400
    assert b'name="selected_project_id" value="p1"' in r.content
    assert b"/partials/tree?selected_project_id=p1" in r.content
    assert len(repo.list_projects("e1")) == 1


def test_overview_header_shows_status_badge_and_subtitle(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="Research Data Scientist"))
    repo.create_project(
        Project(
            id="p1",
            experience_id="e1",
            project_name="Ad Blindness",
            status="In progress",
        )
    )
    r = client.get("/partials/projects/p1?tab=overview")
    assert r.status_code == 200
    assert b"Ad Blindness" in r.content
    assert b"badge" in r.content
    assert b"In progress" in r.content
    assert b"Google" in r.content
    assert b"Research Data Scientist" in r.content
    assert b"class=\"tab is-active\"" in r.content or b"tab is-active" in r.content


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


def test_right_panel_shows_completeness(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))
    r = client.get("/partials/projects/p1?tab=overview")
    assert r.status_code == 200
    assert b"Completeness" in r.content
    assert b"Needs clarification" in r.content
    assert b"progress__bar" in r.content
    assert b"Problem not set" in r.content or b"overview" in r.content.lower()
    assert b"Paste notes" in r.content
    assert b"Continue interview" not in r.content


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


def test_mark_unknown_dismisses_overview_gap(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))

    r = client.post(
        "/projects/p1/gaps/unknown",
        data={"gap_key": "overview.problem"},
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200
    assert "overview.problem" in CareerRepository(db).list_dismissed_gap_keys("p1")
    assert b"Problem not set" not in r.content


def test_mark_unknown_dismisses_open_question(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))
    repo.create_open_question(
        OpenQuestion(
            id="oq1",
            related_entity_type="project",
            related_entity_id="p1",
            question="What changed?",
        )
    )

    r = client.post(
        "/projects/p1/gaps/unknown",
        data={"gap_key": "open_question.oq1"},
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200
    questions = CareerRepository(db).list_open_questions(status=None)
    assert next(question for question in questions if question.id == "oq1").status == "dismissed"
    assert b"What changed?" not in r.content


def test_answer_form_expands_for_gap(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))

    r = client.get(
        "/projects/p1/gaps/answer-form",
        params={"gap_key": "overview.problem"},
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200
    assert b'name="answer"' in r.content
    assert b'name="gap_key" value="overview.problem"' in r.content


def test_answer_now_patches_overview_field(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))

    r = client.post(
        "/projects/p1/gaps/answer",
        data={"gap_key": "overview.problem", "answer": "Users ignore ads"},
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200
    assert CareerRepository(db).get_project("p1").problem == "Users ignore ads"
    assert b"Problem not set" not in r.content


def test_answer_now_patches_contribution_ownership_and_refreshes_center(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))
    repo.create_contribution(Contribution(id="c1", project_id="p1", action="Led study"))

    r = client.post(
        "/projects/p1/gaps/answer",
        data={
            "gap_key": "contribution.c1.ownership_level",
            "answer": "Accountable owner",
        },
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200
    assert CareerRepository(db).get_contribution("c1").ownership_level == "Accountable owner"
    assert b'id="center-panel" hx-swap-oob="true"' in r.content
    assert b"Accountable owner" in r.content


def test_answer_now_routes_coverage_to_agent_and_refreshes_matching_leaf_tab(
    tmp_path, monkeypatch
):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))
    calls = {}

    class FakeAgent:
        def extract_from_notes(self, notes, *, project_id=None):
            calls["notes"] = notes
            calls["project_id"] = project_id
            CareerRepository(db).create_contribution(
                Contribution(id="c1", project_id="p1", action="Led study")
            )
            return {"created": {"contributions": 1}, "updated": {}, "conflicts": []}

    monkeypatch.setattr(ui_app, "build_agent", lambda repo: FakeAgent())
    r = client.post(
        "/projects/p1/gaps/answer",
        data={"gap_key": "coverage.contributions", "answer": "I led the ad blindness study."},
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200
    assert calls == {"notes": "I led the ad blindness study.", "project_id": "p1"}
    assert len(CareerRepository(db).list_contributions("p1")) == 1
    assert b"No contributions recorded" not in r.content
    assert b'id="center-panel" hx-swap-oob="true"' in r.content
    assert b"Led study" in r.content


def test_answer_now_resolves_open_question_after_import(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))
    repo.create_open_question(
        OpenQuestion(
            id="oq1",
            related_entity_type="project",
            related_entity_id="p1",
            question="What changed?",
        )
    )
    calls = {}

    class FakeAgent:
        def extract_from_notes(self, notes, *, project_id=None):
            calls["notes"] = notes
            calls["project_id"] = project_id
            return {"created": {}, "updated": {}, "conflicts": []}

    monkeypatch.setattr(ui_app, "build_agent", lambda repo: FakeAgent())
    r = client.post(
        "/projects/p1/gaps/answer",
        data={"gap_key": "open_question.oq1", "answer": "We reduced ad frequency."},
        headers={"HX-Request": "true"},
    )

    assert r.status_code == 200
    assert calls == {
        "notes": "Question: What changed?\nAnswer: We reduced ad frequency.",
        "project_id": "p1",
    }
    questions = CareerRepository(db).list_open_questions(status=None)
    assert next(question for question in questions if question.id == "oq1").status == "resolved"
    assert b'id="center-panel" hx-swap-oob="true"' in r.content


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


def test_add_experience_validation_preserves_selected_project(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))

    r = client.post(
        "/experiences",
        data={
            "organization": "   ",
            "title": "SWE",
            "selected_project_id": "p1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert b'name="selected_project_id" value="p1"' in r.content
    assert b"/partials/tree?selected_project_id=p1" in r.content
    assert len(CareerRepository(db).list_experiences()) == 1


def test_tree_marks_selected_project(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))
    repo.create_project(Project(id="p2", experience_id="e1", project_name="Ads"))

    r = client.get("/partials/tree?selected_project_id=p1")
    assert r.status_code == 200
    assert b'class="tree-project is-selected"' in r.content or b"tree-project is-selected" in r.content
    assert b"Search" in r.content


def test_project_overview_oob_selects_tree_project(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))

    r = client.get("/partials/projects/p1?tab=overview&q=Ad")
    assert r.status_code == 200
    assert b'id="tree-panel"' in r.content
    assert b"hx-swap-oob" in r.content
    assert b"tree-project is-selected" in r.content
    oob_tree = r.content.split(b'id="tree-panel"', 1)[1].split(b"</aside>", 1)[0]
    assert b'<details open>' in oob_tree
    assert b"Google" in oob_tree
    assert b'value="Ad"' in oob_tree

