from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ai_builder import AIBuilderClient
from .config import RESUME_DIR
from .import_apply import apply_import_payload
from .profile import load_profile, now_iso, save_profile
from .prompts import (
    INTERVIEW_SYSTEM,
    JD_ANALYST_SCHEMA,
    JD_ANALYST_SYSTEM,
    KNOWLEDGE_BUILDER_SCHEMA,
    KNOWLEDGE_BUILDER_SYSTEM,
    RESUME_SCHEMA,
    RESUME_SYSTEM,
    TRUTH_CHECK_SCHEMA,
    TRUTH_CHECK_SYSTEM,
)
from .repository import CareerRepository


_LEAF_LOOKUP: dict[str, tuple[str, str, str]] = {
    "contributions": ("contribution", "action", "list_contributions"),
    "results": ("result", "metric_name", "list_results"),
    "skill_evidence": ("skill_evidence", "skill", "list_skill_evidence"),
    "stories": ("story", "competency", "list_stories"),
}


def _resolve_entity_ids(repo: CareerRepository, payload: dict[str, Any]) -> dict[str, list[str]]:
    """Re-resolve the ids of entities named in an already-applied payload.

    apply_import_payload does not report back the ids it created/matched, so
    open_questions referencing a null related_entity_id (e.g. "the project I
    just described") are resolved here by re-running the same key lookups
    against the now-committed rows, in payload traversal order.
    """
    ids_by_type: dict[str, list[str]] = {}
    for experience_payload in payload.get("experiences", []):
        experience = repo.find_experience_by_key(
            experience_payload.get("organization"),
            experience_payload.get("title"),
            experience_payload.get("start_date"),
        )
        if experience is None:
            continue
        ids_by_type.setdefault("experience", []).append(experience.id)
        for project_payload in experience_payload.get("projects", []):
            project = repo.find_project_by_key(experience.id, project_payload.get("project_name"))
            if project is None:
                continue
            ids_by_type.setdefault("project", []).append(project.id)
            for plural_key, (entity_type, soft_key, list_method) in _LEAF_LOOKUP.items():
                items = getattr(repo, list_method)(project.id)
                for leaf_payload in project_payload.get(plural_key, []):
                    soft_value = leaf_payload.get(soft_key)
                    match = next((item for item in items if getattr(item, soft_key) == soft_value), None)
                    if match is not None:
                        ids_by_type.setdefault(entity_type, []).append(match.id)
    return ids_by_type


def _resolve_question_entity(
    question_payload: dict[str, Any],
    created_ids_by_type: dict[str, list[str]],
    scoped_ids_by_type: dict[str, list[str]],
    *,
    local_type: str | None = None,
    local_id: str | None = None,
) -> dict[str, Any] | None:
    """Resolve a null question id without changing its declared entity type."""
    entity_type = question_payload.get("related_entity_type")
    entity_id = question_payload.get("related_entity_id")
    if entity_id is not None:
        return question_payload

    if entity_type == local_type and local_id is not None:
        candidates = [local_id]
    elif scoped_ids_by_type.get(entity_type):
        candidates = scoped_ids_by_type[entity_type]
    else:
        candidates = created_ids_by_type.get(entity_type, [])
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1:
        return None
    return {**question_payload, "related_entity_id": candidates[0]}


class CareerKnowledgeBuilderAgent:
    def __init__(self, client: AIBuilderClient, repo: CareerRepository) -> None:
        self.client = client
        self.repo = repo

    def extract_from_notes(
        self,
        notes: str,
        *,
        project_id: str | None = None,
        experience_id: str | None = None,
    ) -> dict[str, Any]:
        prior_ids_by_type = {
            "experience": {item.id for item in self.repo.list_experiences()},
            "project": {item.id for item in self.repo.list_projects()},
            **{
                entity_type: {
                    item.id for item in getattr(self.repo, list_method)()
                }
                for entity_type, _, list_method in _LEAF_LOOKUP.values()
            },
        }
        existing_graph = self.repo.graph_summary(experience_id=experience_id, project_id=project_id)
        user = json.dumps(
            {"existing_graph": existing_graph, "notes": notes},
            indent=2,
            ensure_ascii=False,
        )
        response = self.client.chat_json(
            system=KNOWLEDGE_BUILDER_SYSTEM,
            user=user,
            schema_hint=KNOWLEDGE_BUILDER_SCHEMA,
            max_tokens=8000,
        )
        result = apply_import_payload(
            self.repo,
            {"experiences": response.get("experiences", [])},
            project_id=project_id,
            experience_id=experience_id,
        )

        resolved_ids = _resolve_entity_ids(self.repo, response)
        created_ids_by_type = {
            entity_type: list(
                dict.fromkeys(
                    entity_id
                    for entity_id in entity_ids
                    if entity_id not in prior_ids_by_type.get(entity_type, set())
                )
            )
            for entity_type, entity_ids in resolved_ids.items()
        }
        scoped_ids_by_type: dict[str, list[str]] = {}
        if project_id is not None:
            scoped_ids_by_type["project"] = [project_id]
            scoped_project = self.repo.get_project(project_id)
            if scoped_project is not None:
                scoped_ids_by_type["experience"] = [scoped_project.experience_id]
        elif experience_id is not None:
            scoped_ids_by_type["experience"] = [experience_id]

        pending_questions: list[dict[str, Any]] = []
        for experience_payload in response.get("experiences", []):
            experience = self.repo.find_experience_by_key(
                experience_payload.get("organization"),
                experience_payload.get("title"),
                experience_payload.get("start_date"),
            )
            if experience is None:
                continue
            for question_payload in experience_payload.get("open_questions", []):
                resolved_question = _resolve_question_entity(
                    question_payload,
                    created_ids_by_type,
                    scoped_ids_by_type,
                    local_type="experience",
                    local_id=experience.id,
                )
                if resolved_question is not None:
                    pending_questions.append(resolved_question)
            for project_payload in experience_payload.get("projects", []):
                project = self.repo.find_project_by_key(
                    experience.id, project_payload.get("project_name")
                )
                if project is None:
                    continue
                for question_payload in project_payload.get("open_questions", []):
                    resolved_question = _resolve_question_entity(
                        question_payload,
                        created_ids_by_type,
                        scoped_ids_by_type,
                        local_type="project",
                        local_id=project.id,
                    )
                    if resolved_question is not None:
                        pending_questions.append(resolved_question)

        for question_payload in response.get("open_questions", []):
            resolved_question = _resolve_question_entity(
                question_payload,
                created_ids_by_type,
                scoped_ids_by_type,
            )
            if resolved_question is not None:
                pending_questions.append(resolved_question)
        if pending_questions:
            questions_result = apply_import_payload(self.repo, {"open_questions": pending_questions})
            result["open_questions"].extend(questions_result["open_questions"])
            result["conflicts"].extend(questions_result["conflicts"])

        profile = response.get("profile") or {}
        if profile:
            existing = load_profile()
            merged = {**existing, **{key: value for key, value in profile.items() if value not in (None, "", [])}}
            save_profile(merged)
        return result

    def generate_interview_questions(self, focus: str | None = None) -> list[str]:
        priority_order = {"high": 0, "medium": 1, "low": 2}
        open_questions = [
            question.question
            for question in sorted(
                self.repo.list_open_questions(),
                key=lambda question: priority_order.get(question.priority, 1),
            )
        ]
        existing_graph = self.repo.graph_summary()
        user = json.dumps(
            {
                "profile": load_profile(),
                "existing_graph": existing_graph,
                "open_questions": open_questions,
                "focus": focus,
            },
            indent=2,
            ensure_ascii=False,
        )
        response = self.client.chat_json(
            system=INTERVIEW_SYSTEM,
            user=user,
            schema_hint='{"questions": ["question 1", "question 2", "question 3", "question 4", "question 5"]}',
            max_tokens=1200,
        )
        extra_questions = list(response.get("questions", []))
        return open_questions + extra_questions


class ResumeTailoringAgent:
    def __init__(self, client: AIBuilderClient, repo: CareerRepository) -> None:
        self.client = client
        self.repo = repo

    def analyze_jd(self, jd: str) -> dict[str, Any]:
        return self.client.chat_json(
            system=JD_ANALYST_SYSTEM,
            user=f"Job description:\n{jd}",
            schema_hint=JD_ANALYST_SCHEMA,
            max_tokens=2500,
        )

    def retrieve_evidence(self, jd_analysis: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        query = json.dumps(jd_analysis, ensure_ascii=False)
        query_embedding = self.client.embed([query])[0]
        matches = self.repo.search_leaves(query_embedding, limit)
        return [
            {"score": round(score, 4), **self.repo.get_leaf_with_parents(entity_type, entity_id)}
            for entity_type, entity_id, score in matches
        ]

    def tailor_resume(self, jd: str, limit: int = 10) -> Path:
        jd_analysis = self.analyze_jd(jd)
        evidence = self.retrieve_evidence(jd_analysis, limit=limit)
        payload = {
            "profile": load_profile(),
            "job_description": jd,
            "job_analysis": jd_analysis,
            "ranked_evidence": evidence,
        }
        resume = self.client.chat_json(
            system=RESUME_SYSTEM,
            user=json.dumps(payload, indent=2, ensure_ascii=False),
            schema_hint=RESUME_SCHEMA,
            max_tokens=6000,
        )
        critique = self.client.chat_json(
            system=TRUTH_CHECK_SYSTEM,
            user=json.dumps({"resume": resume, "evidence": evidence, "job_analysis": jd_analysis}, indent=2, ensure_ascii=False),
            schema_hint=TRUTH_CHECK_SCHEMA,
            max_tokens=3000,
        )
        return save_resume_package(jd=jd, jd_analysis=jd_analysis, evidence=evidence, resume=resume, critique=critique)


def embed_missing_leaves(client: AIBuilderClient, repo: CareerRepository) -> int:
    missing = repo.list_unembedded_leaves()
    if not missing:
        return 0
    texts = [repo.leaf_searchable_text(entity_type, entity_id) for entity_type, entity_id in missing]
    embeddings = client.embed(texts)
    if len(embeddings) != len(missing):
        raise RuntimeError(
            f"Embedding API returned {len(embeddings)} vectors for "
            f"{len(missing)} leaves."
        )
    for (entity_type, entity_id), embedding in zip(missing, embeddings):
        repo.upsert_embedding(entity_type, entity_id, embedding)
    return len(missing)


def save_resume_package(
    *,
    jd: str,
    jd_analysis: dict[str, Any],
    evidence: list[dict[str, Any]],
    resume: dict[str, Any],
    critique: dict[str, Any],
) -> Path:
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_iso().replace(":", "").replace("+0000", "Z")
    target = RESUME_DIR / f"resume_{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "job_description.txt").write_text(jd, encoding="utf-8")
    (target / "jd_analysis.json").write_text(json.dumps(jd_analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    (target / "evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    (target / "resume.md").write_text(resume.get("resume_markdown", ""), encoding="utf-8")
    (target / "resume_package.json").write_text(json.dumps(resume, indent=2, ensure_ascii=False), encoding="utf-8")
    (target / "truth_check.json").write_text(json.dumps(critique, indent=2, ensure_ascii=False), encoding="utf-8")
    return target
