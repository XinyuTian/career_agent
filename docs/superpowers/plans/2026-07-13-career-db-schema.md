# Career DB Schema & Agent Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat JSON evidence store with a SQLite hierarchical career DB, sync Agent 1/2 to it (including merge + leaf embeddings), and ship a minimal local UI for browse + project-scoped note import.

**Architecture:** Stdlib SQLite (`data/career.db`) behind a repository layer; Agent 1 extracts hierarchical JSON and applies deterministic merge rules; leaf rows are embedded for Agent 2 retrieval with parent Project/Experience context; CLI and FastAPI UI share the same agents/repos. LLM calls use AI Builder OpenAPI (`POST /v1/chat/completions`, `POST /v1/embeddings`) with Bearer auth.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, existing `AIBuilderClient`, pytest, FastAPI + Jinja2 + uvicorn.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-13-career-db-schema-design.md`
- Token env: prefer `AI_BUILDER_TOKEN`, also accept `AI_BUILDER_API_KEY`
- Base URL default: `https://space.ai-builders.com/backend`
- OpenAPI source of truth: `https://space.ai-builders.com/backend/openapi.json`
- DB path: `data/career.db` (under gitignored `data/`)
- Keep `data/profile.json` load/save behavior
- No migration from `career_knowledge_base.json`
- No silent scalar overwrites on conflict — keep existing + OpenQuestion
- Embed only: contribution, result, skill_evidence, story
- UI v1: browse Experiences/Projects, create forms, project-scoped Add notes only (no chat/tailor UI)
- Prefer small focused modules; do not invent experience beyond user notes

---

## File map

| File | Responsibility |
|------|----------------|
| `career_agent/config.py` | Settings, paths (`DB_PATH`), token alias loading |
| `career_agent/models.py` | Dataclasses for Experience, Project, Contribution, Result, SkillEvidence, Story, OpenQuestion |
| `career_agent/db.py` | Connect, `init_schema()`, migrations-on-create DDL |
| `career_agent/repository.py` | CRUD, graph summary, leaf search helpers, embedding store |
| `career_agent/merge.py` | Field merge + match helpers (pure functions) |
| `career_agent/import_apply.py` | Apply LLM payload → DB in a transaction |
| `career_agent/prompts.py` | Hierarchical Agent 1 schema + existing Agent 2 prompts |
| `career_agent/agents.py` | Agent 1/2 rewritten against repository |
| `career_agent/ai_builder.py` | Unchanged API shape; ensure Bearer works with token from settings |
| `career_agent/cli.py` | New/updated commands |
| `career_agent/kb.py` | Delete after profile helpers move to `profile.py` |
| `career_agent/profile.py` | `load_profile` / `save_profile` / `now_iso` |
| `career_agent/ui/app.py` | FastAPI routes |
| `career_agent/ui/templates/*.html` | Minimal Jinja pages |
| `tests/test_*.py` | Unit tests |
| `pyproject.toml` | Add deps: pytest, fastapi, uvicorn, jinja2 |
| `.env.example` / `README.md` | Token + schema/UI docs |

---

### Task 1: Config token alias + DB path + test deps

**Files:**
- Modify: `career_agent/config.py`
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: none
- Produces: `DB_PATH: Path`; `Settings.api_key` from `AI_BUILDER_TOKEN` or `AI_BUILDER_API_KEY`; `load_settings()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os
from career_agent.config import DB_PATH, load_settings


def test_db_path_is_under_data(tmp_path, monkeypatch):
    assert DB_PATH.name == "career.db"
    assert DB_PATH.parent.name == "data"


def test_prefers_ai_builder_token(monkeypatch):
    monkeypatch.setenv("AI_BUILDER_TOKEN", "token-from-token")
    monkeypatch.setenv("AI_BUILDER_API_KEY", "token-from-key")
    settings = load_settings()
    assert settings.api_key == "token-from-token"


def test_falls_back_to_api_key(monkeypatch):
    monkeypatch.delenv("AI_BUILDER_TOKEN", raising=False)
    monkeypatch.setenv("AI_BUILDER_API_KEY", "token-from-key")
    settings = load_settings()
    assert settings.api_key == "token-from-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pip install -e ".[dev]" 2>/dev/null; python3 -m pip install pytest -q; PYTHONPATH=. pytest tests/test_config.py -v`

Expected: FAIL (missing `DB_PATH` and/or token preference)

- [ ] **Step 3: Implement config + deps**

Update `career_agent/config.py`:

```python
DB_PATH = DATA_DIR / "career.db"

def load_settings() -> Settings:
    load_dotenv()
    api_key = (
        os.environ.get("AI_BUILDER_TOKEN", "").strip()
        or os.environ.get("AI_BUILDER_API_KEY", "").strip()
    )
    if not api_key:
        raise RuntimeError(
            "Missing AI_BUILDER_TOKEN (or AI_BUILDER_API_KEY). Add it to .env first."
        )
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("AI_BUILDER_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        chat_model=os.environ.get("AI_BUILDER_CHAT_MODEL", "deepseek").strip() or "deepseek",
        embedding_model=os.environ.get("AI_BUILDER_EMBEDDING_MODEL", "text-embedding-3-small").strip()
        or "text-embedding-3-small",
    )
```

Update `.env.example`:

```bash
AI_BUILDER_TOKEN=your_token_here
# AI_BUILDER_API_KEY=your_key_here
AI_BUILDER_BASE_URL=https://space.ai-builders.com/backend
AI_BUILDER_CHAT_MODEL=deepseek
AI_BUILDER_EMBEDDING_MODEL=text-embedding-3-small
```

Update `pyproject.toml` dependencies / optional:

```toml
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]
ui = ["fastapi>=0.115", "uvicorn>=0.32", "jinja2>=3.1"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `PYTHONPATH=. pytest tests/test_config.py -v`

- [ ] **Step 5: Commit**

```bash
git add career_agent/config.py .env.example pyproject.toml tests/test_config.py
git commit -m "feat: prefer AI_BUILDER_TOKEN and expose DB_PATH"
```

---

### Task 2: Profile helpers extraction

**Files:**
- Create: `career_agent/profile.py`
- Modify: callers later; for now move `now_iso`, `load_profile`, `save_profile` out of `kb.py`
- Test: `tests/test_profile.py`

**Interfaces:**
- Produces: `now_iso() -> str`, `load_profile(path=...) -> dict`, `save_profile(profile, path=...)`

- [ ] **Step 1: Write failing test**

```python
# tests/test_profile.py
from career_agent.profile import load_profile, save_profile


def test_profile_roundtrip(tmp_path):
    path = tmp_path / "profile.json"
    save_profile({"name": "Ada"}, path=path)
    assert load_profile(path=path)["name"] == "Ada"
```

- [ ] **Step 2: Run — expect FAIL** (module missing)

Run: `PYTHONPATH=. pytest tests/test_profile.py -v`

- [ ] **Step 3: Create `career_agent/profile.py`** with the moved implementations from current `kb.py` (same behavior, accept `path`).

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/profile.py tests/test_profile.py
git commit -m "refactor: extract profile helpers"
```

---

### Task 3: Models + SQLite schema

**Files:**
- Create: `career_agent/models.py`
- Create: `career_agent/db.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: dataclasses `Experience`, `Project`, `Contribution`, `Result`, `SkillEvidence`, `Story`, `OpenQuestion` with fields from the spec; `connect(path) -> sqlite3.Connection`; `init_schema(conn) -> None`
- `LEAF_TYPES = ("contribution", "result", "skill_evidence", "story")`

- [ ] **Step 1: Write failing schema smoke test**

```python
# tests/test_schema.py
from career_agent.db import connect, init_schema


def test_init_schema_creates_tables(tmp_path):
    db = tmp_path / "career.db"
    conn = connect(db)
    init_schema(conn)
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
    # FK cascade experience -> project
    conn.execute(
        "INSERT INTO experiences (id, organization, title, start_date, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("e1", "Acme", "SWE", "2020-01", "t", "t"),
    )
    conn.execute(
        "INSERT INTO projects (id, experience_id, project_name, created_at, updated_at) VALUES (?,?,?,?,?)",
        ("p1", "e1", "Platform", "t", "t"),
    )
    conn.commit()
    conn.execute("DELETE FROM experiences WHERE id='e1'")
    conn.commit()
    assert conn.execute("SELECT count(*) FROM projects").fetchone()[0] == 0
    conn.close()
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement models + DDL**

`career_agent/db.py` must:
- `connect(path)` with `PRAGMA foreign_keys = ON`
- create all tables with columns from the spec
- unique indexes: experiences `(organization, title, start_date)`, projects `(experience_id, project_name)`, skill_evidence `(project_id, skill)`
- embeddings PK `(entity_type, entity_id)`
- `ON DELETE CASCADE` for project→experience and leaves→project

Include JSON text columns for `responsibilities`, `collaborators`. `is_estimate INTEGER DEFAULT 0`. `independently_used INTEGER` nullable.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/models.py career_agent/db.py tests/test_schema.py
git commit -m "feat: add SQLite schema and career entity models"
```

---

### Task 4: Repository CRUD + graph summary

**Files:**
- Create: `career_agent/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `connect`, `init_schema`, models
- Produces:
  - `class CareerRepository:`
  - `__init__(self, path: Path | None = None)`
  - `create_experience` / `get_experience` / `list_experiences` / `update_experience`
  - `create_project` / `get_project` / `list_projects` / `update_project`
  - leaf create/get/list/update for contributions, results, skill_evidence, stories
  - `create_open_question` / `list_open_questions(status="open")`
  - `find_experience_by_key(organization, title, start_date) -> Experience | None`
  - `find_project_by_key(experience_id, project_name) -> Project | None`
  - `find_skill_evidence(project_id, skill) -> SkillEvidence | None`
  - `graph_summary(experience_id=None, project_id=None) -> dict` compact for Agent 1
  - embedding: `upsert_embedding`, `delete_embedding`, `list_unembedded_leaves`, `search_leaves(query_embedding, limit) -> list[tuple[entity_type, entity_id, score]]`
  - `leaf_searchable_text(entity_type, entity_id) -> str`
  - `get_leaf_with_parents(entity_type, entity_id) -> dict`
  - `counts() -> dict`

- [ ] **Step 1: Write failing tests** for create/list experience+project, unique finders, cascade counts helper skeleton

```python
# tests/test_repository.py
from career_agent.models import Experience, Project
from career_agent.repository import CareerRepository


def test_create_and_find_experience(tmp_path):
    repo = CareerRepository(tmp_path / "career.db")
    exp = Experience(
        id="e1",
        organization="Acme",
        title="SWE",
        start_date="2020-01",
    )
    repo.create_experience(exp)
    found = repo.find_experience_by_key("Acme", "SWE", "2020-01")
    assert found is not None
    assert found.id == "e1"


def test_graph_summary_includes_ids(tmp_path):
    repo = CareerRepository(tmp_path / "career.db")
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    repo.create_project(
        Project(id="p1", experience_id="e1", project_name="Platform")
    )
    summary = repo.graph_summary()
    assert summary["experiences"][0]["id"] == "e1"
    assert summary["projects"][0]["id"] == "p1"
```

(Use dataclass defaults for `created_at`/`updated_at` via `now_iso` in model `__post_init__` or factory.)

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement repository** (include all methods listed in Interfaces; keep SQL in this file only)

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/repository.py career_agent/models.py tests/test_repository.py
git commit -m "feat: add CareerRepository CRUD and graph summary"
```

---

### Task 5: Merge helpers

**Files:**
- Create: `career_agent/merge.py`
- Test: `tests/test_merge.py`

**Interfaces:**
- Produces:
  - `is_empty(value) -> bool`
  - `merge_scalar(existing, incoming) -> tuple[Any, str | None]`  
    returns `(value, None)` or `(existing, conflict_message)` when both non-empty and differ
  - `merge_list(existing: list, incoming: list) -> list` unique union preserving order
  - `merge_record(existing: dict, incoming: dict, list_fields: set[str]) -> tuple[dict, list[str]]`  
    returns merged dict + list of conflict messages

- [ ] **Step 1: Write failing tests**

```python
# tests/test_merge.py
from career_agent.merge import merge_list, merge_record, merge_scalar


def test_merge_scalar_fills_empty():
    value, conflict = merge_scalar(None, "x")
    assert value == "x" and conflict is None


def test_merge_scalar_conflict_keeps_existing():
    value, conflict = merge_scalar("old", "new")
    assert value == "old"
    assert conflict is not None


def test_merge_list_unions():
    assert merge_list(["a"], ["a", "b"]) == ["a", "b"]


def test_merge_record_reports_conflicts():
    merged, conflicts = merge_record(
        {"title": "A", "team": None, "responsibilities": ["x"]},
        {"title": "B", "team": "Platform", "responsibilities": ["y"]},
        list_fields={"responsibilities"},
    )
    assert merged["title"] == "A"
    assert merged["team"] == "Platform"
    assert merged["responsibilities"] == ["x", "y"]
    assert len(conflicts) == 1
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `merge.py`**

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/merge.py tests/test_merge.py
git commit -m "feat: add field merge helpers with conflict detection"
```

---

### Task 6: Import apply (transactional merge into DB)

**Files:**
- Create: `career_agent/import_apply.py`
- Test: `tests/test_import_apply.py`

**Interfaces:**
- Consumes: `CareerRepository`, merge helpers, models
- Produces:
  - `apply_import_payload(repo, payload: dict, *, project_id: str | None = None, experience_id: str | None = None) -> dict`
  - Return shape: `{"created": {...counts...}, "updated": {...}, "open_questions": [..], "conflicts": [..]}`
  - Match order per spec: exact key → valid in-scope id → create; id/key conflict → OpenQuestion, no overwrite
  - On leaf text change: `delete_embedding`
  - Wrap in SQLite transaction (`BEGIN`/`COMMIT`/`ROLLBACK`)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_import_apply.py
from career_agent.import_apply import apply_import_payload
from career_agent.models import Experience, Project
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
        Project(id="p1", experience_id="e1", project_name="Platform", problem="old")
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
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `import_apply.py`** supporting nested payload OR flat lists keyed by parent ids. Prefer nested under experiences→projects→leaves as in tests. Honor `project_id` scope: reject or ignore experiences/projects outside that project; when scoped, only upsert children for that project.

Raise `ValueError` if scoped id unknown.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/import_apply.py tests/test_import_apply.py
git commit -m "feat: apply hierarchical import payloads with merge rules"
```

---

### Task 7: Agent 1 prompts + extract_from_notes

**Files:**
- Modify: `career_agent/prompts.py`
- Modify: `career_agent/agents.py`
- Test: `tests/test_agent1_import.py`

**Interfaces:**
- Consumes: `AIBuilderClient.chat_json`, `CareerRepository`, `apply_import_payload`, `graph_summary`, profile helpers
- Produces:
  - `KNOWLEDGE_BUILDER_SYSTEM` / `KNOWLEDGE_BUILDER_SCHEMA` hierarchical
  - `CareerKnowledgeBuilderAgent.extract_from_notes(notes, *, project_id=None, experience_id=None) -> dict`
  - `CareerKnowledgeBuilderAgent.generate_interview_questions(focus=None) -> list[str]` including open questions first

- [ ] **Step 1: Write failing unit test with fake client**

```python
# tests/test_agent1_import.py
from career_agent.agents import CareerKnowledgeBuilderAgent
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
    assert repo.list_projects()
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Replace prompts + rewrite Agent 1** to pass `graph_summary` into the user message; call `apply_import_payload`; merge profile via `load_profile`/`save_profile`. Remove `EvidenceRecord` usage.

For `generate_interview_questions`: prepend `repo.list_open_questions()` text, then LLM extras.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/prompts.py career_agent/agents.py tests/test_agent1_import.py
git commit -m "feat: sync Agent 1 import to hierarchical SQLite graph"
```

---

### Task 8: Leaf embeddings + Agent 2 retrieval

**Files:**
- Modify: `career_agent/agents.py` (`embed_missing_records` → `embed_missing_leaves`, `ResumeTailoringAgent`)
- Test: `tests/test_agent2_retrieve.py`

**Interfaces:**
- Produces:
  - `embed_missing_leaves(client, repo) -> int`
  - `ResumeTailoringAgent.retrieve_evidence(jd_analysis, limit=10) -> list[dict]` each item: `{score, entity_type, entity_id, leaf, project, experience}`
  - `tailor_resume` uses that evidence payload

- [ ] **Step 1: Write failing test**

```python
# tests/test_agent2_retrieve.py
from career_agent.agents import ResumeTailoringAgent
from career_agent.models import Contribution, Experience, Project
from career_agent.repository import CareerRepository


class FakeEmbedClient:
    def embed(self, texts):
        # one-hot-ish: longer text => slightly different; fixed vector for assert
        return [[float(len(t))] + [0.0] * 3 for t in texts]


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
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement embedding + tailor retrieval**; delete old JSON KB helpers from agents; update `save_resume_package` unchanged aside from evidence shape.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/agents.py career_agent/repository.py tests/test_agent2_retrieve.py
git commit -m "feat: retrieve resume evidence from leaf embeddings"
```

---

### Task 9: CLI rewrite + remove flat KB

**Files:**
- Modify: `career_agent/cli.py`
- Delete: `career_agent/kb.py` (after ensuring no imports)
- Modify: any leftover imports
- Test: `tests/test_cli_status.py` (subprocess or call `main`)

**Interfaces:**
- Commands per spec: `import-notes` (+ `--project-id`, `--experience-id`), `questions`, `embed`, `tailor`, `status`, `list-experiences`, `list-projects`, `ui` (stub ok until Task 10)

- [ ] **Step 1: Write failing CLI test**

```python
# tests/test_cli_status.py
from career_agent.cli import main
from career_agent.models import Experience
from career_agent.repository import CareerRepository
from career_agent.config import DB_PATH
import career_agent.config as config


def test_status_lists_counts(tmp_path, monkeypatch, capsys):
    db = tmp_path / "career.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    repo = CareerRepository(db)
    repo.create_experience(
        Experience(id="e1", organization="Acme", title="SWE", start_date="2020")
    )
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "experiences: 1" in out.lower() or "Experiences: 1" in out
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement CLI**; print status like:

```
Experiences: N
Projects: N
Contributions: N
Results: N
Skill evidence: N
Stories: N
Open questions: N
Embedded leaves: N
```

Remove `CareerKnowledgeBase` imports. Add `ui` subparser that imports `career_agent.ui.app:run` (implement stub raising clear message if UI deps missing until Task 10).

- [ ] **Step 4: Run unit tests + `python -m career_agent.cli status`** against temp DB if needed — expect PASS

- [ ] **Step 5: Commit**

```bash
git add career_agent/cli.py tests/test_cli_status.py
git rm -f career_agent/kb.py
git commit -m "feat: point CLI at SQLite career repository"
```

---

### Task 10: Minimal FastAPI UI

**Files:**
- Create: `career_agent/ui/__init__.py`
- Create: `career_agent/ui/app.py`
- Create: `career_agent/ui/templates/base.html`
- Create: `career_agent/ui/templates/experiences.html`
- Create: `career_agent/ui/templates/experience_detail.html`
- Create: `career_agent/ui/templates/project_detail.html`
- Create: `career_agent/ui/templates/open_questions.html`
- Modify: `career_agent/cli.py` (`ui` command)
- Modify: `pyproject.toml` (ensure `ui` extras)
- Test: `tests/test_ui.py` with `TestClient`

**Interfaces:**
- Produces: `create_app() -> FastAPI`; `run(host="127.0.0.1", port=8765)`
- Routes:
  - `GET /` experiences list + create form
  - `POST /experiences` create
  - `GET /experiences/{id}` detail + create project form
  - `POST /experiences/{id}/projects` create project
  - `GET /projects/{id}` detail + notes form + leaf sections
  - `POST /projects/{id}/notes` scoped Agent 1 import (needs API key; test with monkeypatched agent)
  - `GET /open-questions`

- [ ] **Step 1: Write failing UI tests**

```python
# tests/test_ui.py
from fastapi.testclient import TestClient
from career_agent.ui.app import create_app
import career_agent.ui.app as ui_app


def test_home_lists_experiences(tmp_path, monkeypatch):
    db = tmp_path / "career.db"
    monkeypatch.setattr(ui_app, "DB_PATH", db)
    client = TestClient(create_app(db_path=db))
    r = client.get("/")
    assert r.status_code == 200
    assert b"Experiences" in r.content


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
```

- [ ] **Step 2: Run — expect FAIL** (install `pip install -e ".[ui,dev]"` first)

- [ ] **Step 3: Implement UI** — functional local tool aesthetic (simple HTML, no card-heavy marketing). Flash messages for import results. On notes POST, call `CareerKnowledgeBuilderAgent.extract_from_notes(..., project_id=...)`.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui pyproject.toml career_agent/cli.py tests/test_ui.py
git commit -m "feat: add minimal local UI for experiences and project notes"
```

---

### Task 11: README sync + full regression

**Files:**
- Modify: `README.md`
- Optionally add `httpx` via fastapi testclient already depending on it

- [ ] **Step 1: Update README** to document SQLite schema entities, new CLI flags, `career-agent ui`, `AI_BUILDER_TOKEN`, and remove flat JSON KB docs.

- [ ] **Step 2: Run full test suite**

Run: `PYTHONPATH=. pytest -v`  
Expected: all PASS

- [ ] **Step 3: Manual smoke (optional if token present)**

```bash
career-agent status
career-agent ui
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for SQLite career DB and UI"
```

- [ ] **Step 5: Commit any remaining untracked package baseline if still untracked** (`career_agent/ai_builder.py`, etc.) so the repo is coherent:

```bash
git add career_agent .gitignore pyproject.toml .env.example README.md
git status
# commit only if there are leftover related files not yet committed
git commit -m "chore: track career_agent package baseline"
```

---

## Spec coverage checklist (self-review)

| Spec requirement | Task |
|------------------|------|
| SQLite tables for 7 entities + embeddings | 3–4 |
| Hybrid import + OpenQuestions | 6–7 |
| Exact key then LLM id then create; ambiguity → OpenQuestion | 6 |
| Scalar conflict keep existing + OpenQuestion | 5–6 |
| Leaf embeddings only | 8 |
| Agent 2 parent context | 8 |
| CLI flags + list/status | 9 |
| Minimal UI browse + scoped notes | 10 |
| OpenAPI Bearer + token alias | 1 |
| profile.json kept | 2, 7 |
| README | 11 |

## Placeholder / consistency notes

- Repository method names in Tasks 4–10 must match (`create_contribution`, `upsert_embedding`, etc.).
- `CareerKnowledgeBuilderAgent` constructor becomes `(client, repo: CareerRepository)`.
- Do not leave dual writes to JSON KB.
