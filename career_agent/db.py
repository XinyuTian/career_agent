from __future__ import annotations

import sqlite3
from os import PathLike
from pathlib import Path


def connect(path: str | PathLike[str]) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS experiences (
            id TEXT PRIMARY KEY,
            organization TEXT NOT NULL,
            title TEXT NOT NULL,
            employment_type TEXT,
            start_date TEXT,
            end_date TEXT,
            team TEXT,
            manager_level TEXT,
            business_context TEXT,
            reason_for_joining TEXT,
            reason_for_leaving TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_experiences_match
            ON experiences (organization, title, start_date);

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            experience_id TEXT NOT NULL
                REFERENCES experiences(id) ON DELETE CASCADE,
            project_name TEXT NOT NULL,
            problem TEXT,
            business_context TEXT,
            users_or_stakeholders TEXT,
            personal_role TEXT,
            responsibilities TEXT,
            project_stage TEXT,
            timeline TEXT,
            status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_match
            ON projects (experience_id, project_name);

        CREATE TABLE IF NOT EXISTS contributions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            technical_method TEXT,
            decision_made TEXT,
            difficulty TEXT,
            alternative_considered TEXT,
            collaborators TEXT,
            ownership_level TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS results (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(id) ON DELETE CASCADE,
            result_type TEXT,
            metric_name TEXT,
            baseline TEXT,
            final_value TEXT,
            absolute_change TEXT,
            relative_change TEXT,
            business_impact TEXT,
            confidence_level TEXT,
            measurement_method TEXT,
            is_estimate INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_evidence (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(id) ON DELETE CASCADE,
            skill TEXT NOT NULL,
            proficiency TEXT,
            evidence TEXT,
            recency TEXT,
            frequency TEXT,
            independently_used INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_skill_evidence_match
            ON skill_evidence (project_id, skill);

        CREATE TABLE IF NOT EXISTS stories (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(id) ON DELETE CASCADE,
            competency TEXT,
            situation TEXT,
            task TEXT,
            action TEXT,
            result TEXT,
            conflict TEXT,
            lesson TEXT,
            what_you_would_change TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS open_questions (
            id TEXT PRIMARY KEY,
            related_entity_type TEXT NOT NULL,
            related_entity_id TEXT NOT NULL,
            question TEXT NOT NULL,
            why_it_matters TEXT,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            embedding TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id)
        );

        CREATE TRIGGER IF NOT EXISTS cleanup_experience_open_questions
        AFTER DELETE ON experiences
        BEGIN
            DELETE FROM open_questions
            WHERE related_entity_type = 'experience'
              AND related_entity_id = OLD.id;
        END;

        CREATE TRIGGER IF NOT EXISTS cleanup_project_open_questions
        AFTER DELETE ON projects
        BEGIN
            DELETE FROM open_questions
            WHERE related_entity_type = 'project'
              AND related_entity_id = OLD.id;
        END;

        CREATE TRIGGER IF NOT EXISTS cleanup_contribution_open_questions
        AFTER DELETE ON contributions
        BEGIN
            DELETE FROM open_questions
            WHERE related_entity_type = 'contribution'
              AND related_entity_id = OLD.id;
        END;

        CREATE TRIGGER IF NOT EXISTS cleanup_result_open_questions
        AFTER DELETE ON results
        BEGIN
            DELETE FROM open_questions
            WHERE related_entity_type = 'result'
              AND related_entity_id = OLD.id;
        END;

        CREATE TRIGGER IF NOT EXISTS cleanup_skill_evidence_open_questions
        AFTER DELETE ON skill_evidence
        BEGIN
            DELETE FROM open_questions
            WHERE related_entity_type = 'skill_evidence'
              AND related_entity_id = OLD.id;
        END;

        CREATE TRIGGER IF NOT EXISTS cleanup_story_open_questions
        AFTER DELETE ON stories
        BEGIN
            DELETE FROM open_questions
            WHERE related_entity_type = 'story'
              AND related_entity_id = OLD.id;
        END;
        """
    )
