import career_agent.config as config
from career_agent.cli import main
from career_agent.models import Experience, Project
from career_agent.repository import CareerRepository


def test_status_lists_counts(tmp_path, monkeypatch, capsys):
    db = tmp_path / "career.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    repo = CareerRepository(db)
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert "Experiences: 1" in out
    assert "Projects: 0" in out
    assert "Embedded leaves: 0" in out


def test_list_projects_can_filter_by_experience(tmp_path, monkeypatch, capsys):
    db = tmp_path / "career.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_experience(Experience(id="e2", organization="Beta", title="Staff SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))
    repo.create_project(Project(id="p2", experience_id="e2", project_name="Payments"))

    assert main(["list-projects", "--experience-id", "e1"]) == 0

    out = capsys.readouterr().out
    assert "p1" in out
    assert "Search" in out
    assert "p2" not in out
