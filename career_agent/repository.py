from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any, TypeVar

from .config import DB_PATH
from .db import connect, init_schema
from .models import (
    LEAF_TYPES,
    Contribution,
    Experience,
    OpenQuestion,
    Project,
    Result,
    SkillEvidence,
    Story,
)
from .profile import now_iso


Model = TypeVar(
    "Model",
    Experience,
    Project,
    Contribution,
    Result,
    SkillEvidence,
    Story,
    OpenQuestion,
)

_MODEL_TABLES: dict[type[Any], str] = {
    Experience: "experiences",
    Project: "projects",
    Contribution: "contributions",
    Result: "results",
    SkillEvidence: "skill_evidence",
    Story: "stories",
    OpenQuestion: "open_questions",
}
_LEAF_MODELS: dict[str, type[Contribution | Result | SkillEvidence | Story]] = {
    "contribution": Contribution,
    "result": Result,
    "skill_evidence": SkillEvidence,
    "story": Story,
}
_LIST_FIELDS = {
    (Project, "responsibilities"),
    (Contribution, "collaborators"),
}
_BOOL_FIELDS = {
    (Result, "is_estimate"),
    (SkillEvidence, "independently_used"),
}


class CareerRepository:
    def __init__(self, path: Path | None = None):
        self.path = path or DB_PATH
        self.conn = connect(self.path)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.commit()
        self.conn.isolation_level = None

    def _to_database(self, model: Model) -> dict[str, Any]:
        values = asdict(model)
        model_type = type(model)
        for field_name, value in values.items():
            if (model_type, field_name) in _LIST_FIELDS:
                values[field_name] = json.dumps(value)
            elif (model_type, field_name) in _BOOL_FIELDS and value is not None:
                values[field_name] = int(value)
        return values

    def _from_row(self, model_type: type[Model], row: sqlite3.Row | None) -> Model | None:
        if row is None:
            return None
        values = dict(row)
        for field_name, value in values.items():
            if (model_type, field_name) in _LIST_FIELDS:
                values[field_name] = json.loads(value) if value else []
            elif (model_type, field_name) in _BOOL_FIELDS and value is not None:
                values[field_name] = bool(value)
        return model_type(**values)

    def _create(self, model: Model) -> None:
        table = _MODEL_TABLES[type(model)]
        values = self._to_database(model)
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        self.conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )

    def _get(self, model_type: type[Model], entity_id: str) -> Model | None:
        table = _MODEL_TABLES[model_type]
        row = self.conn.execute(
            f"SELECT * FROM {table} WHERE id = ?",
            (entity_id,),
        ).fetchone()
        return self._from_row(model_type, row)

    def _list(
        self,
        model_type: type[Model],
        *,
        parent_field: str | None = None,
        parent_id: str | None = None,
    ) -> list[Model]:
        table = _MODEL_TABLES[model_type]
        sql = f"SELECT * FROM {table}"
        params: tuple[Any, ...] = ()
        if parent_field is not None and parent_id is not None:
            sql += f" WHERE {parent_field} = ?"
            params = (parent_id,)
        sql += " ORDER BY id"
        return [
            self._from_row(model_type, row)
            for row in self.conn.execute(sql, params).fetchall()
        ]

    def _update(self, model: Model) -> None:
        table = _MODEL_TABLES[type(model)]
        values = self._to_database(model)
        values["updated_at"] = now_iso()
        entity_id = values.pop("id")
        assignments = ", ".join(f"{name} = ?" for name in values)
        cursor = self.conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            (*values.values(), entity_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"{table} record not found: {entity_id}")

    def create_experience(self, experience: Experience) -> None:
        self._create(experience)

    def get_experience(self, experience_id: str) -> Experience | None:
        return self._get(Experience, experience_id)

    def list_experiences(self) -> list[Experience]:
        return self._list(Experience)

    def update_experience(self, experience: Experience) -> None:
        self._update(experience)

    def create_project(self, project: Project) -> None:
        self._create(project)

    def get_project(self, project_id: str) -> Project | None:
        return self._get(Project, project_id)

    def list_projects(self, experience_id: str | None = None) -> list[Project]:
        return self._list(
            Project,
            parent_field="experience_id",
            parent_id=experience_id,
        )

    def update_project(self, project: Project) -> None:
        self._update(project)

    def duplicate_project(self, project_id: str) -> Project | None:
        original = self.get_project(project_id)
        if original is None:
            return None
        new_name = f"{original.project_name} (copy)"
        attempt = 2
        while self.find_project_by_key(original.experience_id, new_name) is not None:
            new_name = f"{original.project_name} (copy {attempt})"
            attempt += 1
        new_project = replace(
            original,
            id=str(uuid.uuid4()),
            project_name=new_name,
            status=None,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self.create_project(new_project)
        for contribution in self.list_contributions(project_id):
            self.create_contribution(
                replace(
                    contribution,
                    id=str(uuid.uuid4()),
                    project_id=new_project.id,
                    created_at=now_iso(),
                    updated_at=now_iso(),
                )
            )
        for result in self.list_results(project_id):
            self.create_result(
                replace(
                    result,
                    id=str(uuid.uuid4()),
                    project_id=new_project.id,
                    created_at=now_iso(),
                    updated_at=now_iso(),
                )
            )
        for evidence in self.list_skill_evidence(project_id):
            self.create_skill_evidence(
                replace(
                    evidence,
                    id=str(uuid.uuid4()),
                    project_id=new_project.id,
                    created_at=now_iso(),
                    updated_at=now_iso(),
                )
            )
        for story in self.list_stories(project_id):
            self.create_story(
                replace(
                    story,
                    id=str(uuid.uuid4()),
                    project_id=new_project.id,
                    created_at=now_iso(),
                    updated_at=now_iso(),
                )
            )
        return new_project

    def create_contribution(self, contribution: Contribution) -> None:
        self._create(contribution)

    def get_contribution(self, contribution_id: str) -> Contribution | None:
        return self._get(Contribution, contribution_id)

    def list_contributions(self, project_id: str | None = None) -> list[Contribution]:
        return self._list(
            Contribution,
            parent_field="project_id",
            parent_id=project_id,
        )

    def update_contribution(self, contribution: Contribution) -> None:
        self._update(contribution)

    def delete_contribution(self, contribution_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM contributions WHERE id = ?", (contribution_id,))
        deleted = cur.rowcount > 0
        if deleted:
            self.delete_embedding("contribution", contribution_id)
        self.conn.commit()
        return deleted

    def create_result(self, result: Result) -> None:
        self._create(result)

    def get_result(self, result_id: str) -> Result | None:
        return self._get(Result, result_id)

    def list_results(self, project_id: str | None = None) -> list[Result]:
        return self._list(Result, parent_field="project_id", parent_id=project_id)

    def update_result(self, result: Result) -> None:
        self._update(result)

    def delete_result(self, result_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM results WHERE id = ?", (result_id,))
        deleted = cur.rowcount > 0
        if deleted:
            self.delete_embedding("result", result_id)
        self.conn.commit()
        return deleted

    def create_skill_evidence(self, evidence: SkillEvidence) -> None:
        self._create(evidence)

    def get_skill_evidence(self, evidence_id: str) -> SkillEvidence | None:
        return self._get(SkillEvidence, evidence_id)

    def list_skill_evidence(
        self,
        project_id: str | None = None,
    ) -> list[SkillEvidence]:
        return self._list(
            SkillEvidence,
            parent_field="project_id",
            parent_id=project_id,
        )

    def update_skill_evidence(self, evidence: SkillEvidence) -> None:
        self._update(evidence)

    def delete_skill_evidence(self, evidence_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM skill_evidence WHERE id = ?", (evidence_id,))
        deleted = cur.rowcount > 0
        if deleted:
            self.delete_embedding("skill_evidence", evidence_id)
        self.conn.commit()
        return deleted

    def create_story(self, story: Story) -> None:
        self._create(story)

    def get_story(self, story_id: str) -> Story | None:
        return self._get(Story, story_id)

    def list_stories(self, project_id: str | None = None) -> list[Story]:
        return self._list(Story, parent_field="project_id", parent_id=project_id)

    def update_story(self, story: Story) -> None:
        self._update(story)

    def delete_story(self, story_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        deleted = cur.rowcount > 0
        if deleted:
            self.delete_embedding("story", story_id)
        self.conn.commit()
        return deleted

    def create_open_question(self, question: OpenQuestion) -> None:
        self._create(question)

    def update_open_question(self, question: OpenQuestion) -> None:
        self._update(question)

    def dismiss_gap(self, project_id: str, gap_key: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO dismissed_gaps (project_id, gap_key, created_at)
            VALUES (?, ?, ?)
            """,
            (project_id, gap_key, now_iso()),
        )

    def list_dismissed_gap_keys(self, project_id: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT gap_key FROM dismissed_gaps WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        return {row["gap_key"] for row in rows}

    def list_open_questions(
        self,
        status: str | None = "open",
    ) -> list[OpenQuestion]:
        sql = "SELECT * FROM open_questions"
        params: tuple[Any, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY id"
        return [
            self._from_row(OpenQuestion, row)
            for row in self.conn.execute(sql, params).fetchall()
        ]

    def find_experience_by_key(
        self,
        organization: str,
        title: str,
        start_date: str | None,
    ) -> Experience | None:
        row = self.conn.execute(
            """
            SELECT * FROM experiences
            WHERE organization = ? AND title = ? AND start_date IS ?
            """,
            (organization, title, start_date),
        ).fetchone()
        return self._from_row(Experience, row)

    def find_project_by_key(
        self,
        experience_id: str,
        project_name: str,
    ) -> Project | None:
        row = self.conn.execute(
            """
            SELECT * FROM projects
            WHERE experience_id = ? AND project_name = ?
            """,
            (experience_id, project_name),
        ).fetchone()
        return self._from_row(Project, row)

    def find_skill_evidence(
        self,
        project_id: str,
        skill: str,
    ) -> SkillEvidence | None:
        row = self.conn.execute(
            """
            SELECT * FROM skill_evidence
            WHERE project_id = ? AND skill = ?
            """,
            (project_id, skill),
        ).fetchone()
        return self._from_row(SkillEvidence, row)

    def graph_summary(
        self,
        experience_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        projects = self.list_projects(experience_id)
        if project_id is not None:
            project = self.get_project(project_id)
            projects = (
                [project]
                if project is not None
                and (experience_id is None or project.experience_id == experience_id)
                else []
            )

        if project_id is not None or experience_id is not None:
            experience_ids = {project.experience_id for project in projects}
            if (
                experience_id is not None
                and (project_id is None or projects)
                and self.get_experience(experience_id) is not None
            ):
                experience_ids.add(experience_id)
            experiences = [
                experience
                for entity_id in sorted(experience_ids)
                if (experience := self.get_experience(entity_id)) is not None
            ]
        else:
            experiences = self.list_experiences()

        project_ids = {project.id for project in projects}
        leaves: dict[str, list[Any]] = {
            "contributions": self.list_contributions(),
            "results": self.list_results(),
            "skill_evidence": self.list_skill_evidence(),
            "stories": self.list_stories(),
        }
        if project_id is not None or experience_id is not None:
            leaves = {
                name: [leaf for leaf in rows if leaf.project_id in project_ids]
                for name, rows in leaves.items()
            }

        entity_ids = {
            ("experience", experience.id) for experience in experiences
        } | {("project", project.id) for project in projects}
        for entity_type, plural_name in (
            ("contribution", "contributions"),
            ("result", "results"),
            ("skill_evidence", "skill_evidence"),
            ("story", "stories"),
        ):
            entity_ids.update((entity_type, leaf.id) for leaf in leaves[plural_name])
        questions = self.list_open_questions(None)
        if project_id is not None or experience_id is not None:
            questions = [
                question
                for question in questions
                if (question.related_entity_type, question.related_entity_id)
                in entity_ids
            ]

        return {
            "experiences": [self._compact(item) for item in experiences],
            "projects": [self._compact(item) for item in projects],
            **{
                name: [self._compact(item) for item in rows]
                for name, rows in leaves.items()
            },
            "open_questions": [self._compact(item) for item in questions],
        }

    def upsert_embedding(
        self,
        entity_type: str,
        entity_id: str,
        embedding: list[float],
    ) -> None:
        model_type = self._leaf_model(entity_type)
        if self._get(model_type, entity_id) is None:
            raise KeyError(f"{entity_type} not found: {entity_id}")
        vector = [float(value) for value in embedding]
        self.conn.execute(
            """
            INSERT INTO embeddings (entity_type, entity_id, embedding, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                embedding = excluded.embedding,
                updated_at = excluded.updated_at
            """,
            (entity_type, entity_id, json.dumps(vector), now_iso()),
        )

    def delete_embedding(self, entity_type: str, entity_id: str) -> None:
        self._leaf_model(entity_type)
        self.conn.execute(
            "DELETE FROM embeddings WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )

    def list_unembedded_leaves(self) -> list[tuple[str, str]]:
        missing: list[tuple[str, str]] = []
        for entity_type in LEAF_TYPES:
            model_type = self._leaf_model(entity_type)
            table = _MODEL_TABLES[model_type]
            rows = self.conn.execute(
                f"""
                SELECT leaf.id
                FROM {table} AS leaf
                WHERE NOT EXISTS (
                    SELECT 1 FROM embeddings
                    WHERE entity_type = ? AND entity_id = leaf.id
                )
                ORDER BY leaf.id
                """,
                (entity_type,),
            ).fetchall()
            missing.extend((entity_type, row["id"]) for row in rows)
        return missing

    def search_leaves(
        self,
        query_embedding: list[float],
        limit: int,
    ) -> list[tuple[str, str, float]]:
        if limit <= 0:
            return []
        query = [float(value) for value in query_embedding]
        matches: list[tuple[str, str, float]] = []
        rows = self.conn.execute(
            "SELECT entity_type, entity_id, embedding FROM embeddings"
        ).fetchall()
        for row in rows:
            if row["entity_type"] not in _LEAF_MODELS:
                continue
            if self._get(self._leaf_model(row["entity_type"]), row["entity_id"]) is None:
                continue
            vector = json.loads(row["embedding"])
            if len(vector) != len(query):
                continue
            score = self._cosine_similarity(query, vector)
            matches.append((row["entity_type"], row["entity_id"], score))
        matches.sort(key=lambda item: (-item[2], item[0], item[1]))
        return matches[:limit]

    def leaf_searchable_text(self, entity_type: str, entity_id: str) -> str:
        model_type = self._leaf_model(entity_type)
        leaf = self._get(model_type, entity_id)
        if leaf is None:
            raise KeyError(f"{entity_type} not found: {entity_id}")
        project = self.get_project(leaf.project_id)
        if project is None:
            raise KeyError(f"project not found: {leaf.project_id}")
        experience = self.get_experience(project.experience_id)
        if experience is None:
            raise KeyError(f"experience not found: {project.experience_id}")
        excluded = {"id", "project_id", "created_at", "updated_at"}
        parts: list[str] = []
        for model_field in fields(leaf):
            if model_field.name in excluded:
                continue
            value = getattr(leaf, model_field.name)
            if value is None or value == "" or value == []:
                continue
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            else:
                parts.append(str(value))
        parts.extend(
            [project.project_name, experience.organization, experience.title]
        )
        return "\n".join(parts)

    def get_leaf_with_parents(
        self,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any]:
        model_type = self._leaf_model(entity_type)
        leaf = self._get(model_type, entity_id)
        if leaf is None:
            raise KeyError(f"{entity_type} not found: {entity_id}")
        project = self.get_project(leaf.project_id)
        if project is None:
            raise KeyError(f"project not found: {leaf.project_id}")
        experience = self.get_experience(project.experience_id)
        if experience is None:
            raise KeyError(f"experience not found: {project.experience_id}")
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "leaf": asdict(leaf),
            "project": asdict(project),
            "experience": asdict(experience),
        }

    def counts(self) -> dict[str, int]:
        tables = (
            "experiences",
            "projects",
            "contributions",
            "results",
            "skill_evidence",
            "stories",
            "open_questions",
            "embeddings",
        )
        return {
            table: self.conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in tables
        }

    @staticmethod
    def _compact(model: Any) -> dict[str, Any]:
        return {
            name: value
            for name, value in asdict(model).items()
            if name not in {"created_at", "updated_at"}
            and value not in (None, "", [])
        }

    @staticmethod
    def _leaf_model(
        entity_type: str,
    ) -> type[Contribution | Result | SkillEvidence | Story]:
        try:
            return _LEAF_MODELS[entity_type]
        except KeyError as error:
            raise ValueError(f"Unsupported leaf type: {entity_type}") from error

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
