from unittest.mock import Mock

import pytest

from career_agent.import_apply import apply_import_payload
from career_agent.models import Contribution, Experience, Project
from career_agent.repository import CareerRepository


def test_creates_hierarchy(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    result = apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": None,
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "projects": [
                        {
                            "id": None,
                            "project_name": "Platform",
                            "contributions": [
                                {"id": None, "action": "Built CI"},
                            ],
                        }
                    ],
                }
            ],
            "open_questions": [],
        },
    )
    assert result["created"]["experiences"] == 1
    assert result["created"]["projects"] == 1
    assert result["created"]["contributions"] == 1
    assert len(repo.list_experiences()) == 1


def test_merges_existing_project_by_key(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_project(
        Project(id="p1", experience_id="e1", project_name="Platform", problem=None)
    )
    result = apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "projects": [
                        {
                            "id": None,
                            "project_name": "Platform",
                            "problem": "new problem",
                        }
                    ],
                }
            ]
        },
    )
    assert result["updated"]["projects"] == 1
    assert repo.get_project("p1").problem == "new problem"


def test_key_match_scalar_conflict_keeps_existing_and_opens_question(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_project(
        Project(id="p1", experience_id="e1", project_name="Platform", problem="old")
    )

    apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "projects": [
                        {
                            "id": None,
                            "project_name": "Platform",
                            "problem": "new problem",
                        }
                    ],
                }
            ]
        },
    )

    assert repo.get_project("p1").problem == "old"
    opens = repo.list_open_questions(status="open")
    assert len(opens) >= 1


def test_scalar_conflict_keeps_existing_and_opens_question(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(
            id="e1",
            organization="Acme",
            title="SWE",
            start_date="2020",
            team="Infra",
        )
    )
    apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "team": "Data",
                }
            ]
        },
    )
    assert repo.get_experience("e1").team == "Infra"
    opens = repo.list_open_questions(status="open")
    assert len(opens) >= 1


def test_unknown_scoped_project_id_raises(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")

    with pytest.raises(ValueError):
        apply_import_payload(repo, {"experiences": []}, project_id="missing")


def test_unknown_scoped_experience_id_raises(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")

    with pytest.raises(ValueError):
        apply_import_payload(repo, {"experiences": []}, experience_id="missing")


def test_explicit_project_id_under_wrong_experience_does_not_update(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_experience(
        Experience(id="e2", organization="Other", title="SWE", start_date="2021")
    )
    repo.create_project(
        Project(id="p2", experience_id="e2", project_name="Foreign", problem=None)
    )

    result = apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "projects": [
                        {
                            "id": "p2",
                            "project_name": "Foreign",
                            "problem": "must not overwrite",
                        }
                    ],
                }
            ]
        },
    )

    assert repo.get_project("p2").problem is None
    assert result["conflicts"]


def test_project_scope_ignores_payload_for_another_experience(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_experience(
        Experience(
            id="e2",
            organization="Other",
            title="SWE",
            start_date="2021",
            team=None,
        )
    )
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Scoped"))

    apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e2",
                    "organization": "Other",
                    "title": "SWE",
                    "start_date": "2021",
                    "team": "must not overwrite",
                }
            ]
        },
        project_id="p1",
    )

    assert repo.get_experience("e2").team is None


def test_project_scope_only_upserts_scoped_project_leaves(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(
            id="e1",
            organization="Acme",
            title="SWE",
            start_date="2020",
            team="Infra",
        )
    )
    repo.create_project(
        Project(
            id="p1",
            experience_id="e1",
            project_name="Scoped",
            problem="Original problem",
        )
    )
    repo.update_experience = Mock(wraps=repo.update_experience)
    repo.update_project = Mock(wraps=repo.update_project)

    result = apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "team": "Data",
                    "projects": [
                        {
                            "id": "p1",
                            "project_name": "Scoped",
                            "problem": "Replacement problem",
                            "contributions": [
                                {"id": "c1", "action": "Built project scope"}
                            ],
                        }
                    ],
                }
            ]
        },
        project_id="p1",
    )

    repo.update_experience.assert_not_called()
    repo.update_project.assert_not_called()
    assert repo.get_experience("e1").team == "Infra"
    assert repo.get_project("p1").problem == "Original problem"
    assert repo.get_contribution("c1").action == "Built project scope"
    assert result["created"]["contributions"] == 1


def test_rejected_scalar_conflict_keeps_embedding(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Scoped"))
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Original action")
    )
    repo.upsert_embedding("contribution", "c1", [1.0, 0.0])

    apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "projects": [
                        {
                            "id": "p1",
                            "project_name": "Scoped",
                            "contributions": [
                                {"id": "c1", "action": "Reworded action"}
                            ],
                        }
                    ],
                }
            ]
        },
    )

    assert repo.get_contribution("c1").action == "Original action"
    assert repo.list_unembedded_leaves() == []


def test_leaf_fill_deletes_embedding_when_searchable_text_changes(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Scoped"))
    repo.create_contribution(
        Contribution(
            id="c1",
            project_id="p1",
            action="Original action",
            technical_method=None,
        )
    )
    repo.upsert_embedding("contribution", "c1", [1.0, 0.0])

    apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "projects": [
                        {
                            "id": "p1",
                            "project_name": "Scoped",
                            "contributions": [
                                {
                                    "id": "c1",
                                    "action": "Original action",
                                    "technical_method": "new method",
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )

    assert repo.get_contribution("c1").technical_method == "new method"
    assert repo.list_unembedded_leaves() == [("contribution", "c1")]


def test_explicit_leaf_id_under_wrong_project_does_not_update(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Scoped"))
    repo.create_project(Project(id="p2", experience_id="e1", project_name="Foreign"))
    repo.create_contribution(
        Contribution(
            id="c2",
            project_id="p2",
            action="Foreign action",
            technical_method=None,
        )
    )

    result = apply_import_payload(
        repo,
        {
            "experiences": [
                {
                    "id": "e1",
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2020",
                    "projects": [
                        {
                            "id": "p1",
                            "project_name": "Scoped",
                            "contributions": [
                                {
                                    "id": "c2",
                                    "action": "Foreign action",
                                    "technical_method": "must not overwrite",
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )

    assert repo.get_contribution("c2").technical_method is None
    assert result["conflicts"]
