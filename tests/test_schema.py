import sqlite3

import pytest

from career_agent.db import connect, init_schema


@pytest.fixture
def schema_conn(tmp_path):
    db = tmp_path / "career.db"
    conn = connect(db)
    init_schema(conn)
    yield conn
    conn.close()


def test_connect_creates_parent_directory(tmp_path):
    db = tmp_path / "data" / "career.db"

    conn = connect(db)

    assert db.exists()
    conn.close()


def test_init_schema_creates_tables(schema_conn):
    conn = schema_conn
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "experiences",
        "projects",
        "contributions",
        "results",
        "skill_evidence",
        "stories",
        "open_questions",
        "embeddings",
    } <= tables


def test_schema_enforces_foreign_keys_unique_indexes_and_embedding_key(schema_conn):
    conn = schema_conn

    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    }
    assert {
        "ux_experiences_match",
        "ux_projects_match",
        "ux_skill_evidence_match",
    } <= indexes

    embedding_pk = [
        row[1]
        for row in conn.execute("PRAGMA table_info(embeddings)")
        if row[5]
    ]
    assert embedding_pk == ["entity_type", "entity_id"]

    conn.execute(
        "INSERT INTO embeddings VALUES (?, ?, ?, ?)",
        ("project", "p1", "[]", "t"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO embeddings VALUES (?, ?, ?, ?)",
            ("project", "p1", "[1]", "t"),
        )


def test_project_delete_cascades_to_contribution(schema_conn):
    conn = schema_conn
    conn.execute(
        "INSERT INTO experiences (id, organization, title, start_date, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("e1", "Acme", "SWE", "2020-01", "t", "t"),
    )
    conn.execute(
        "INSERT INTO projects (id, experience_id, project_name, created_at, updated_at) VALUES (?,?,?,?,?)",
        ("p1", "e1", "Platform", "t", "t"),
    )
    conn.execute(
        "INSERT INTO contributions (id, project_id, action, created_at, updated_at) VALUES (?,?,?,?,?)",
        ("c1", "p1", "Built it", "t", "t"),
    )
    conn.commit()
    conn.execute("DELETE FROM projects WHERE id='p1'")
    conn.commit()

    assert conn.execute("SELECT count(*) FROM contributions").fetchone()[0] == 0


def test_deletes_clean_up_related_open_questions(schema_conn):
    conn = schema_conn
    conn.execute(
        "INSERT INTO experiences (id, organization, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        ("e1", "Acme", "SWE", "t", "t"),
    )
    conn.executemany(
        "INSERT INTO projects (id, experience_id, project_name, created_at, updated_at) VALUES (?,?,?,?,?)",
        [
            ("p1", "e1", "Platform", "t", "t"),
            ("p2", "e1", "API", "t", "t"),
        ],
    )
    conn.execute(
        "INSERT INTO contributions (id, project_id, action, created_at, updated_at) VALUES (?,?,?,?,?)",
        ("c1", "p1", "Built it", "t", "t"),
    )
    conn.executemany(
        "INSERT INTO open_questions (id, related_entity_type, related_entity_id, question, priority, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("q-exp", "experience", "e1", "Experience?", "high", "open", "t", "t"),
            ("q-proj", "project", "p1", "Project?", "high", "open", "t", "t"),
            ("q-leaf", "contribution", "c1", "Contribution?", "high", "open", "t", "t"),
            ("q-direct-proj", "project", "p2", "Other project?", "high", "open", "t", "t"),
            ("q-unrelated", "project", "other", "Unrelated?", "high", "open", "t", "t"),
        ],
    )
    conn.commit()

    conn.execute("DELETE FROM contributions WHERE id = 'c1'")
    conn.execute("DELETE FROM projects WHERE id = 'p2'")
    conn.execute("DELETE FROM experiences WHERE id = 'e1'")
    conn.commit()

    assert conn.execute(
        "SELECT id FROM open_questions ORDER BY id"
    ).fetchall() == [("q-unrelated",)]
