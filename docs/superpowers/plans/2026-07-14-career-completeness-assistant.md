# Career Completeness Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project completeness assistant to the workspace right panel: hybrid gap scoring, hover-revealed Answer now / Mark as unknown, dismissed_gaps persistence, stacked above existing Paste notes.

**Architecture:** Pure `completeness.py` builds checklist/missing/% from repository snapshots. SQLite gains `dismissed_gaps`; repository gains dismiss + update OpenQuestion status. FastAPI/HTMX right-panel partial renders the assistant; POST endpoints handle unknown/answer and refresh the panel (OOB center when data changes).

**Tech Stack:** Python 3.11+, existing SQLite/FastAPI/Jinja/HTMX workspace, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-14-career-completeness-assistant-design.md`
- Hybrid gaps: structural rules + open OpenQuestions only (no LLM scoring)
- Hover (and focus-within) reveals Answer now / Mark as unknown; Answer now expands inline form
- Mark unknown: OQ → `dismissed`; structural → `dismissed_gaps`
- Score excludes dismissed items from checklist
- Completeness stacked above Paste notes
- No interviewer chat; no clear-dismissed UI; project-scoped only
- Preserve existing Paste notes import behavior

---

## File map

| File | Responsibility |
|------|----------------|
| `career_agent/db.py` | `dismissed_gaps` table DDL |
| `career_agent/repository.py` | dismiss CRUD; `update_open_question` |
| `career_agent/completeness.py` | Gap models + `evaluate_project_completeness` |
| `career_agent/ui/app.py` | Wire right panel + unknown/answer routes |
| `career_agent/ui/templates/partials/right_notes.html` → rename/split into `right_panel.html` + completeness + notes includes |
| `career_agent/ui/templates/partials/completeness.html` | % + missing list + hover actions + answer form |
| `tests/test_completeness.py` | Engine unit tests |
| `tests/test_ui.py` | Right-panel + action integration tests |
| `README.md` | Mention completeness assistant |

---

### Task 1: `dismissed_gaps` schema + repository helpers

**Files:**
- Modify: `career_agent/db.py`
- Modify: `career_agent/repository.py`
- Test: `tests/test_repository.py` (or `tests/test_dismissed_gaps.py`)

**Interfaces:**
- Consumes: `init_schema`, `CareerRepository`
- Produces:
  - table `dismissed_gaps(project_id, gap_key, created_at)` PK `(project_id, gap_key)`
  - `dismiss_gap(self, project_id: str, gap_key: str) -> None`
  - `list_dismissed_gap_keys(self, project_id: str) -> set[str]`
  - `update_open_question(self, question: OpenQuestion) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_dismiss_gap_roundtrip(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE", start_date="2020"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="P"))
    repo.dismiss_gap("p1", "overview.problem")
    assert "overview.problem" in repo.list_dismissed_gap_keys("p1")
    repo.dismiss_gap("p1", "overview.problem")  # idempotent
    assert repo.list_dismissed_gap_keys("p1") == {"overview.problem"}


def test_update_open_question_status(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE", start_date="2020"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="P"))
    q = OpenQuestion(id="q1", related_entity_type="project", related_entity_id="p1", question="Metric?")
    repo.create_open_question(q)
    q.status = "dismissed"
    repo.update_open_question(q)
    assert repo.list_open_questions(status="dismissed")[0].id == "q1"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv/bin/pytest tests/test_repository.py -k dismiss -v` (or new file)

- [ ] **Step 3: Implement DDL + methods**

In `init_schema`, add:

```sql
CREATE TABLE IF NOT EXISTS dismissed_gaps (
    project_id TEXT NOT NULL,
    gap_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, gap_key)
);
```

`dismiss_gap` uses `INSERT OR IGNORE`. Cascade: optional `ON DELETE CASCADE` from projects if FK added — prefer FK `project_id REFERENCES projects(id) ON DELETE CASCADE`.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/db.py career_agent/repository.py tests/
git commit -m "feat: persist dismissed completeness gaps"
```

---

### Task 2: Completeness evaluation engine

**Files:**
- Create: `career_agent/completeness.py`
- Test: `tests/test_completeness.py`

**Interfaces:**
- Consumes: models + repo read methods (or pass in already-loaded project/leaves/questions/dismissed)
- Produces:

```python
@dataclass(frozen=True)
class GapItem:
    key: str
    label: str
    kind: str  # overview_field | coverage | leaf_field | open_question
    passed: bool
    # optional metadata for answer routing:
    field_name: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    open_question_id: str | None = None


@dataclass(frozen=True)
class CompletenessReport:
    percent: int
    missing: list[GapItem]  # failed items only
    checklist: list[GapItem]  # all remaining after dismiss filter


def evaluate_project_completeness(
    *,
    project: Project,
    contributions: list[Contribution],
    results: list[Result],
    skills: list[SkillEvidence],
    stories: list[Story],
    open_questions: list[OpenQuestion],
    dismissed_keys: set[str],
) -> CompletenessReport: ...
```

Use exact structural keys/labels from the spec.

- [ ] **Step 1: Write failing tests**

```python
def test_empty_project_missing_overview_and_coverage():
    project = Project(id="p1", experience_id="e1", project_name="Ad Blindness")
    report = evaluate_project_completeness(
        project=project,
        contributions=[],
        results=[],
        skills=[],
        stories=[],
        open_questions=[],
        dismissed_keys=set(),
    )
    keys = {g.key for g in report.missing}
    assert "overview.problem" in keys
    assert "coverage.contributions" in keys
    assert report.percent < 100


def test_dismissed_key_excluded_from_score():
    project = Project(id="p1", experience_id="e1", project_name="P", problem="x", business_context="x", personal_role="x", users_or_stakeholders="x")
    # still missing coverage etc.
    base = evaluate_project_completeness(project=project, contributions=[], results=[], skills=[], stories=[], open_questions=[], dismissed_keys=set())
    dismissed = evaluate_project_completeness(project=project, contributions=[], results=[], skills=[], stories=[], open_questions=[], dismissed_keys={"coverage.contributions"})
    assert "coverage.contributions" not in {g.key for g in dismissed.missing}
    assert dismissed.percent >= base.percent


def test_open_question_appears_as_missing():
    project = Project(id="p1", experience_id="e1", project_name="P", problem="x", business_context="x", personal_role="x", users_or_stakeholders="x")
    q = OpenQuestion(id="q1", related_entity_type="project", related_entity_id="p1", question="What was the latency win?")
    report = evaluate_project_completeness(
        project=project,
        contributions=[Contribution(id="c1", project_id="p1", action="Built CI", ownership_level="owner")],
        results=[Result(id="r1", project_id="p1", metric_name="latency", baseline="10", final_value="5")],
        skills=[SkillEvidence(id="s1", project_id="p1", skill="SQL", evidence="wrote queries")],
        stories=[Story(id="t1", project_id="p1", situation="x")],
        open_questions=[q],
        dismissed_keys=set(),
    )
    assert any(g.key == "open_question.q1" for g in report.missing)
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `completeness.py` per Score section of the spec**

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/completeness.py tests/test_completeness.py
git commit -m "feat: add hybrid project completeness evaluation"
```

---

### Task 3: Right panel completeness UI (read-only display)

**Files:**
- Create: `career_agent/ui/templates/partials/completeness.html`
- Modify: `career_agent/ui/templates/partials/right_notes.html` (or introduce `right_panel.html` that includes completeness + notes)
- Modify: `career_agent/ui/app.py` — helper to build report + pass into right panel context wherever `right_notes.html` is rendered
- Test: `tests/test_ui.py`

**Interfaces:**
- When `project` set: compute `CompletenessReport` and pass `completeness=report`
- Template shows `Project completeness: {{ completeness.percent }}%` and Missing list
- Gap rows include CSS class for hover actions placeholders (buttons can be present but inactive until Task 4 — or include markup with `hx-post` stubs). Prefer showing actions markup in Task 3 disabled/hidden via CSS, wired in Task 4.
- Paste notes section remains below

- [ ] **Step 1: Write failing test**

```python
def test_right_panel_shows_completeness(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))
    r = client.get("/partials/projects/p1?tab=overview")
    assert r.status_code == 200
    assert b"Project completeness" in r.content
    assert b"Problem not set" in r.content or b"overview" in r.content.lower()
    assert b"Paste notes" in r.content
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement rendering helper `_right_panel_context(repo, project)` and update templates**

CSS in `workspace.html` for `.gap-row .gap-actions { opacity: 0 }` / `.gap-row:hover .gap-actions, .gap-row:focus-within .gap-actions { opacity: 1 }` — buttons can be non-functional placeholders labeled correctly for Task 3, or full HTMX wired in Task 4 only. **Prefer markup structure in Task 3; wire POSTs in Task 4.**

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui tests/test_ui.py
git commit -m "feat: show project completeness in right panel"
```

---

### Task 4: Mark as unknown + Answer now

**Files:**
- Modify: `career_agent/ui/app.py`
- Modify: `partials/completeness.html`
- Optional: `career_agent/ui/gap_actions.py` if app.py too large
- Test: `tests/test_ui.py`

**Interfaces:**
- `POST /projects/{project_id}/gaps/{gap_key}/unknown` → dismiss; return updated right panel fragment (`#right-panel`)
- `GET /projects/{project_id}/gaps/{gap_key}/answer` → return gap row expanded with answer form (HTMX swap on that row or whole right panel)
- `POST /projects/{project_id}/gaps/{gap_key}/answer` with `answer` form field → apply write path from spec; return right panel (+ OOB center overview when overview field patched)

URL-encode gap keys carefully (`contribution.<uuid>.ownership_level`). Prefer passing `gap_key` as a form field to avoid slash issues:

**Adjusted routes (normative for implementers):**
- `POST /projects/{project_id}/gaps/unknown` body: `gap_key`
- `POST /projects/{project_id}/gaps/answer` body: `gap_key`, `answer`
- `GET /projects/{project_id}/gaps/answer-form?gap_key=...` for expand form

- [ ] **Step 1: Write failing tests**

```python
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
```

Also test OpenQuestion dismiss → status dismissed (can use fake agent for OQ answer path in a separate test).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement action handlers**

Routing table from GapItem metadata:

- `kind == overview_field` + `field_name` → `replace(project, **{field_name: answer})` + `update_project`
- `kind == leaf_field` → load entity, replace field, update_*
- `kind == coverage` → `build_agent(repo).extract_from_notes(answer, project_id=...)`
- `kind == open_question` → import `Question: ...\nAnswer: ...`; set OQ status resolved

Return `_render_right_panel(...)` with optional OOB center.

Wire completeness.html:
- Mark as unknown: `hx-post` unknown
- Answer now: `hx-get` answer-form
- Answer form submit: `hx-post` answer

- [ ] **Step 4: Run UI + completeness tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui tests/test_ui.py
git commit -m "feat: answer and dismiss completeness gaps from right panel"
```

---

### Task 5: README + regression

**Files:**
- Modify: `README.md`
- Ensure notes import tests still pass with stacked layout

- [ ] **Step 1: Document completeness assistant in README** (right panel gaps, hover actions, paste notes still below)

- [ ] **Step 2: Run full suite**

Run: `.venv/bin/pytest -q`  
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: describe completeness assistant in README"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| dismissed_gaps + OQ status updates | 1 |
| Hybrid evaluation + % | 2 |
| Right panel display stacked over paste notes | 3 |
| Hover/focus-within action reveal CSS | 3–4 |
| Mark unknown / Answer now write paths | 4 |
| README | 5 |
| No interviewer | all |

## Consistency notes

- Use form-field `gap_key` routes (not path-encoded keys with dots).
- `right_notes.html` include sites must all receive `completeness` context (or safe empty when no project).
- OpenQuestion answer success must set `resolved` even if Agent 1 creates additional records.
