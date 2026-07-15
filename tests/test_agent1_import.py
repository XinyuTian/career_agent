import json

from career_agent import agents
from career_agent.agents import CareerKnowledgeBuilderAgent
from career_agent.models import OpenQuestion
from career_agent.repository import CareerRepository


class FakeClient:
    def chat_json(self, **kwargs):
        return {
            "profile": {},
            "experiences": [
                {
                    "id": None,
                    "organization": "Acme",
                    "title": "SWE",
                    "start_date": "2021",
                    "projects": [
                        {
                            "id": None,
                            "project_name": "Search",
                            "contributions": [{"id": None, "action": "Sharded index"}],
                            "results": [],
                            "skill_evidence": [],
                            "stories": [],
                        }
                    ],
                }
            ],
            "open_questions": [
                {
                    "related_entity_type": "project",
                    "related_entity_id": None,
                    "question": "What was the latency win?",
                    "why_it_matters": "Need a metric",
                    "priority": "high",
                    "status": "open",
                }
            ],
        }


def test_extract_from_notes_writes_rows(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    agent = CareerKnowledgeBuilderAgent(FakeClient(), repo)
    out = agent.extract_from_notes("I sharded the search index at Acme.")
    assert out["created"]["contributions"] == 1
    project = repo.list_projects()[0]
    question = repo.list_open_questions()[0]
    assert question.related_entity_type == "project"
    assert question.related_entity_id == project.id


def test_null_project_question_with_two_projects_is_not_coerced_to_experience(tmp_path):
    class TwoProjectClient(FakeClient):
        def chat_json(self, **kwargs):
            response = super().chat_json(**kwargs)
            response["experiences"][0]["projects"].append(
                {
                    "id": None,
                    "project_name": "Recommendations",
                    "contributions": [],
                    "results": [],
                    "skill_evidence": [],
                    "stories": [],
                }
            )
            return response

    repo = CareerRepository(tmp_path / "t.db")
    CareerKnowledgeBuilderAgent(TwoProjectClient(), repo).extract_from_notes("Two projects")

    assert repo.list_open_questions() == []


def test_null_contribution_question_links_only_unique_created_contribution(tmp_path):
    class ContributionQuestionClient(FakeClient):
        def chat_json(self, **kwargs):
            response = super().chat_json(**kwargs)
            response["open_questions"][0]["related_entity_type"] = "contribution"
            return response

    repo = CareerRepository(tmp_path / "t.db")
    CareerKnowledgeBuilderAgent(ContributionQuestionClient(), repo).extract_from_notes(
        "One contribution"
    )

    contribution = repo.list_contributions()[0]
    question = repo.list_open_questions()[0]
    assert question.related_entity_type == "contribution"
    assert question.related_entity_id == contribution.id


def test_null_contribution_question_is_skipped_when_created_set_is_ambiguous(tmp_path):
    class TwoContributionClient(FakeClient):
        def chat_json(self, **kwargs):
            response = super().chat_json(**kwargs)
            response["experiences"][0]["projects"][0]["contributions"].append(
                {"id": None, "action": "Added replicas"}
            )
            response["open_questions"][0]["related_entity_type"] = "contribution"
            return response

    repo = CareerRepository(tmp_path / "t.db")
    CareerKnowledgeBuilderAgent(TwoContributionClient(), repo).extract_from_notes(
        "Two contributions"
    )

    assert repo.list_open_questions() == []


def test_project_nested_question_attaches_to_its_project_with_multiple_projects(tmp_path):
    class NestedQuestionClient(FakeClient):
        def chat_json(self, **kwargs):
            response = super().chat_json(**kwargs)
            response["open_questions"] = []
            response["experiences"][0]["projects"][0]["open_questions"] = [
                {
                    "related_entity_type": "project",
                    "related_entity_id": None,
                    "question": "What was the search impact?",
                    "priority": "high",
                }
            ]
            response["experiences"][0]["projects"].append(
                {"id": None, "project_name": "Recommendations"}
            )
            return response

    repo = CareerRepository(tmp_path / "t.db")
    CareerKnowledgeBuilderAgent(NestedQuestionClient(), repo).extract_from_notes("Two projects")

    projects = {project.project_name: project for project in repo.list_projects()}
    question = repo.list_open_questions()[0]
    assert question.related_entity_id == projects["Search"].id
    assert question.related_entity_id != projects["Recommendations"].id


def test_extract_from_notes_merges_profile_without_erasing_existing_values(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(agents, "load_profile", lambda: {"name": "Ada", "location": "London"})
    monkeypatch.setattr(agents, "save_profile", saved.append)

    class ProfileClient(FakeClient):
        def chat_json(self, **kwargs):
            response = super().chat_json(**kwargs)
            response["profile"] = {"name": "", "headline": "Staff Engineer"}
            return response

    repo = CareerRepository(tmp_path / "t.db")
    CareerKnowledgeBuilderAgent(ProfileClient(), repo).extract_from_notes("Profile update")

    assert saved == [{"name": "Ada", "location": "London", "headline": "Staff Engineer"}]


def test_generate_interview_questions_includes_profile_and_orders_db_questions(tmp_path, monkeypatch):
    class InterviewClient:
        def __init__(self):
            self.user = None

        def chat_json(self, **kwargs):
            self.user = json.loads(kwargs["user"])
            return {"questions": ["LLM extra"]}

    repo = CareerRepository(tmp_path / "t.db")
    for question_id, priority, text in [
        ("q-low", "low", "Low priority"),
        ("q-high", "high", "High priority"),
        ("q-medium", "medium", "Medium priority"),
    ]:
        repo.create_open_question(
            OpenQuestion(
                id=question_id,
                related_entity_type="experience",
                related_entity_id="e1",
                question=text,
                priority=priority,
            )
        )
    monkeypatch.setattr(agents, "load_profile", lambda: {"name": "Ada"})
    client = InterviewClient()

    questions = CareerKnowledgeBuilderAgent(client, repo).generate_interview_questions()

    assert questions == ["High priority", "Medium priority", "Low priority", "LLM extra"]
    assert client.user["profile"] == {"name": "Ada"}
    assert client.user["open_questions"] == questions[:-1]
