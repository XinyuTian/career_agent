import pytest

from career_agent.agents import ResumeTailoringAgent, embed_missing_leaves
from career_agent.models import Contribution, Experience, Project
from career_agent.repository import CareerRepository


class FakeEmbedClient:
    def embed(self, texts):
        # one-hot-ish: longer text => slightly different; fixed vector for assert
        return [[float(len(t))] + [0.0] * 3 for t in texts]


class MissingEmbeddingClient:
    def embed(self, texts):
        return []


def test_retrieve_uses_leaf_embeddings(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Platform"))
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Built CI pipeline")
    )
    text = repo.leaf_searchable_text("contribution", "c1")
    repo.upsert_embedding("contribution", "c1", [float(len(text)), 0.0, 0.0, 0.0])
    agent = ResumeTailoringAgent(FakeEmbedClient(), repo)
    matches = agent.retrieve_evidence({"keywords": ["CI"]}, limit=5)
    assert matches[0]["entity_id"] == "c1"
    assert matches[0]["project"]["id"] == "p1"
    assert matches[0]["experience"]["id"] == "e1"


def test_embed_missing_leaves_rejects_incomplete_embedding_response(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Platform"))
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Built CI pipeline")
    )

    with pytest.raises(RuntimeError, match="returned 0 vectors for 1 leaves"):
        embed_missing_leaves(MissingEmbeddingClient(), repo)
