# Career Workspace UI Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the multi-page UI with a three-panel HTMX career workspace: left navigator, center project tabs with panel Edit/Save/Cancel, right Paste-notes Agent 1 import — using only the existing SQLite models.

**Architecture:** Keep FastAPI + Jinja. Introduce a persistent shell template and HTMX partials for tree, center tabs (read/edit), and right-panel notes results. Repository gains leaf `delete_*` methods for Edit-mode removals. Old multi-page templates are retired once the workspace routes work.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX (CDN), existing `CareerRepository` / `CareerKnowledgeBuilderAgent`, pytest + TestClient.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-14-career-workspace-ui-design.md`
- No new DB tables/columns for Overview
- Overview fields only: `problem`, `business_context`, `personal_role`, `users_or_stakeholders`, `responsibilities`, `project_stage`, `timeline`, `status`
- Experience click expands tree only; center requires project selection
- Panel-level Edit / Save / Cancel (not per-section inline Edit)
- `+ Add experience` under search; `+ Add project` beside each Experience row
- Right panel = Paste notes (scoped Agent 1); Phase 2 completeness/interviewer not built
- Preserve blank-name rejection on create
- HTMX via CDN script tag (no new Python dependency required)
- Functional local-tool aesthetic (no marketing card layout)

---

## File map

| File | Responsibility |
|------|----------------|
| `career_agent/repository.py` | Add `delete_contribution/result/skill_evidence/story` |
| `career_agent/ui/app.py` | Workspace routes + partials; retire old page flows |
| `career_agent/ui/templates/workspace.html` | Three-panel shell |
| `career_agent/ui/templates/partials/tree.html` | Navigator fragment |
| `career_agent/ui/templates/partials/center_placeholder.html` | “Select a project” |
| `career_agent/ui/templates/partials/center_overview_read.html` | Overview read |
| `career_agent/ui/templates/partials/center_overview_edit.html` | Overview edit form |
| `career_agent/ui/templates/partials/center_leaves_read.html` | Leaf tab read |
| `career_agent/ui/templates/partials/center_leaves_edit.html` | Leaf tab edit |
| `career_agent/ui/templates/partials/right_notes.html` | Paste notes panel |
| `career_agent/ui/templates/partials/add_experience_form.html` | Create experience form |
| `career_agent/ui/templates/partials/add_project_form.html` | Create project form |
| Delete (after migration): `experiences.html`, `experience_detail.html`, `project_detail.html`, `open_questions.html` (or keep open-questions as optional link later — Phase 1 may drop dedicated page) |
| `tests/test_ui.py` | Rewrite for workspace behaviors |
| `tests/test_repository.py` | Delete-method tests |
| `pyproject.toml` | Already has `ui` extras; no HTMX package |
| `README.md` | Describe workspace UI |

---

### Task 1: Repository leaf deletes

**Files:**
- Modify: `career_agent/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: existing leaf tables / CASCADE embeddings triggers
- Produces:
  - `delete_contribution(self, contribution_id: str) -> None`
  - `delete_result(self, result_id: str) -> None`
  - `delete_skill_evidence(self, evidence_id: str) -> None`
  - `delete_story(self, story_id: str) -> None`
  - Each deletes the row by id; no-op or raise if missing — prefer silent no-op after checking existence so Save batches are idempotent, OR raise `KeyError` if id unknown. Use: delete and return `bool` deleted.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_repository.py
def test_delete_contribution(tmp_path):
    repo = CareerRepository(tmp_path / "t.db")
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE", start_date="2020"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Platform"))
    repo.create_contribution(Contribution(id="c1", project_id="p1", action="Built CI"))
    assert repo.delete_contribution("c1") is True
    assert repo.list_contributions("p1") == []
    assert repo.delete_contribution("c1") is False
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `.venv/bin/pytest tests/test_repository.py::test_delete_contribution -v`  
Expected: FAIL (`delete_contribution` missing)

- [ ] **Step 3: Implement four delete methods**

```python
def delete_contribution(self, contribution_id: str) -> bool:
    cur = self.conn.execute("DELETE FROM contributions WHERE id = ?", (contribution_id,))
    self.conn.commit()
    return cur.rowcount > 0
```

Mirror for `results`, `skill_evidence`, `stories`.

- [ ] **Step 4: Run tests — expect PASS**

Run: `.venv/bin/pytest tests/test_repository.py -v`

- [ ] **Step 5: Commit**

```bash
git add career_agent/repository.py tests/test_repository.py
git commit -m "feat: add leaf delete methods to CareerRepository"
```

---

### Task 2: Workspace shell + empty state

**Files:**
- Create: `career_agent/ui/templates/workspace.html`
- Create: `career_agent/ui/templates/partials/center_placeholder.html`
- Create: `career_agent/ui/templates/partials/right_notes.html` (disabled empty state)
- Create: `career_agent/ui/templates/partials/tree.html` (empty tree ok)
- Modify: `career_agent/ui/app.py` — `GET /` returns workspace shell
- Modify: `tests/test_ui.py`

**Interfaces:**
- Produces: `GET /` renders three panels; center id=`center-panel`; right id=`right-panel`; tree id=`tree-panel`
- HTMX script from `https://unpkg.com/htmx.org@2.0.4`

- [ ] **Step 1: Write failing test**

```python
def test_workspace_shell_renders_three_panels(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b"id=\"tree-panel\"" in r.content
    assert b"id=\"center-panel\"" in r.content
    assert b"id=\"right-panel\"" in r.content
    assert b"Select a project" in r.content
    assert b"Paste notes" in r.content
```

- [ ] **Step 2: Run — expect FAIL** (old home still says Experiences list)

- [ ] **Step 3: Implement shell**

`workspace.html` structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Career Workspace</title>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <style>/* three-column grid; functional local-tool CSS */</style>
</head>
<body>
  <div class="workspace">
    <aside id="tree-panel">{% include "partials/tree.html" %}</aside>
    <main id="center-panel">{% include "partials/center_placeholder.html" %}</main>
    <aside id="right-panel">{% include "partials/right_notes.html" %}</aside>
  </div>
</body>
</html>
```

`GET /` loads experiences/projects for tree context and returns `workspace.html`.

Keep `create_app(db_path=...)` and `build_agent` / `DB_PATH` patterns.

- [ ] **Step 4: Run new test — expect PASS** (temporarily allow or update old tests that assert old home copy in a follow-up task if they fail — mark failing old tests with clear skips only if needed; prefer update in Step 4 of this task for `test_home_lists_experiences` → rename/assert navigator instead)

Update `test_home_lists_experiences` to assert workspace/search rather than old Experiences page.

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui tests/test_ui.py
git commit -m "feat: add three-panel workspace shell"
```

---

### Task 3: Navigator — search, tree, add experience/project

**Files:**
- Modify: `partials/tree.html`, `app.py`
- Create: `partials/add_experience_form.html`, `partials/add_project_form.html`
- Test: `tests/test_ui.py`

**Interfaces:**
- `GET /partials/tree?q=` — optional filter (server-side filter OK for Phase 1; client-side filter in tree JS also OK — prefer **server filter via `q`** for simpler tests)
- `POST /experiences` — create; returns updated tree fragment (HX-Retarget `#tree-panel`) or 400 with form error
- `POST /experiences/{id}/projects` — create; returns updated tree; reject blank `project_name`
- Tree markup: Experience label + button `+ Add project`; nested project links with `hx-get="/partials/projects/{id}?tab=overview" hx-target="#center-panel"` and also `hx-get` right panel notes for that project (or one endpoint that updates both via `hx-swap-oob`)

**OOB pattern (recommended):** project click response includes center fragment + `hx-swap-oob="true"` right panel for that project_id.

- [ ] **Step 1: Write failing tests**

```python
def test_add_experience_from_workspace(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    r = client.post(
        "/experiences",
        data={"organization": "Google", "title": "SWE", "start_date": "2021"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert b"Google" in r.content
    assert len(CareerRepository(db).list_experiences()) == 1


def test_add_project_beside_experience(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    r = client.post(
        "/experiences/e1/projects",
        data={"project_name": "LTRPM Measurement"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert b"LTRPM Measurement" in r.content
    assert CareerRepository(db).list_projects("e1")[0].project_name == "LTRPM Measurement"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement tree + create endpoints for HTMX**

Tree template sketch:

```html
<input type="search" name="q" placeholder="Search"
       hx-get="/partials/tree" hx-trigger="keyup changed delay:200ms" hx-target="#tree-panel" hx-include="this">
<button hx-get="/partials/add-experience" hx-target="#tree-panel">+ Add experience</button>
{% for exp in experiences %}
  <div class="experience-row">
    <button type="button" class="exp-toggle">{{ exp.organization }} — {{ exp.title }}</button>
    <button hx-get="/partials/experiences/{{ exp.id }}/add-project" hx-target="#tree-panel">+ Add project</button>
  </div>
  <ul class="projects">
    {% for p in projects_by_exp[exp.id] %}
      <li><a href="#"
           hx-get="/partials/projects/{{ p.id }}?tab=overview"
           hx-target="#center-panel">{{ p.project_name }}</a></li>
    {% endfor %}
  </ul>
{% endfor %}
```

Non-HTMX full-page POST may still redirect to `/` for resilience.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui tests/test_ui.py
git commit -m "feat: workspace navigator with add experience and project"
```

---

### Task 4: Center Overview read / Edit / Save / Cancel

**Files:**
- Create: `partials/center_overview_read.html`, `partials/center_overview_edit.html`
- Modify: `app.py`
- Test: `tests/test_ui.py`

**Interfaces:**
- `GET /partials/projects/{project_id}?tab=overview` → read overview (+ tab chrome)
- `GET /partials/projects/{project_id}/edit?tab=overview` → edit form
- `POST /partials/projects/{project_id}?tab=overview` → save fields → return read fragment
- `GET /partials/projects/{project_id}?tab=overview` used as Cancel target

Overview fields only as in Global Constraints. Include counts footer.

When returning project center, also OOB-swap right notes panel for that project.

- [ ] **Step 1: Write failing tests**

```python
def test_overview_read_and_save(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness", problem=None))
    r = client.get("/partials/projects/p1?tab=overview")
    assert r.status_code == 200
    assert b"Ad Blindness" in r.content
    assert b"Not set yet" in r.content or b"Problem" in r.content
    edit = client.get("/partials/projects/p1/edit?tab=overview")
    assert edit.status_code == 200
    assert b"name=\"problem\"" in edit.content
    saved = client.post(
        "/partials/projects/p1?tab=overview",
        data={
            "problem": "Users ignore ads",
            "business_context": "Revenue",
            "personal_role": "Lead",
            "users_or_stakeholders": "PMs",
            "responsibilities": "Design study\nAnalyze results",
            "project_stage": "shipped",
            "timeline": "2022",
            "status": "done",
        },
    )
    assert saved.status_code == 200
    project = CareerRepository(db).get_project("p1")
    assert project.problem == "Users ignore ads"
    assert project.responsibilities == ["Design study", "Analyze results"]
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement overview read/edit/save**

Shared tab chrome partial with links:

`Overview | Contributions | Results | Skills | Stories` each `hx-get` with `tab=`.

Edit button → `hx-get=".../edit?tab=overview"`.  
Save → form `hx-post`. Cancel → `hx-get` read URL.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui tests/test_ui.py
git commit -m "feat: project overview read and panel edit/save"
```

---

### Task 5: Leaf tabs read / Edit / Save

**Files:**
- Create: `partials/center_leaves_read.html`, `partials/center_leaves_edit.html`
- Modify: `app.py`
- Test: `tests/test_ui.py`

**Interfaces:**
- `tab` query: `contributions` | `results` | `skills` | `stories`
- Read lists entities
- Edit form: one subform per existing row (`id` hidden) + empty template row for add; checkbox `delete_<id>` or `delete_ids` multi for removals
- `POST /partials/projects/{id}?tab=contributions` saves batch:
  - update rows with ids
  - create rows with empty id
  - delete checked ids via repository deletes

Map Skills tab ↔ `skill_evidence`.

- [ ] **Step 1: Write failing test**

```python
def test_contributions_tab_save_create(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Incident Analysis"))
    r = client.post(
        "/partials/projects/p1?tab=contributions",
        data={
            "id": [""],
            "action": ["Wrote postmortem"],
            "technical_method": ["Log analysis"],
            "decision_made": [""],
            "difficulty": [""],
            "alternative_considered": [""],
            "collaborators": [""],
            "ownership_level": ["owner"],
        },
    )
    assert r.status_code == 200
    rows = CareerRepository(db).list_contributions("p1")
    assert len(rows) == 1
    assert rows[0].action == "Wrote postmortem"
```

Add a second test that updates an existing contribution and deletes another via `delete_ids`.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement leaf tab handlers**

Keep parsing helpers in `app.py` small; optional `career_agent/ui/forms.py` if `app.py` exceeds ~400 lines — only split if needed.

For list fields (`collaborators`), accept comma- or newline-separated text.

Required: Contribution `action` non-empty for new rows; SkillEvidence `skill` non-empty; skip blank new rows.

- [ ] **Step 4: Run leaf + full UI tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui tests/test_ui.py
git commit -m "feat: leaf tabs with panel edit/save"
```

---

### Task 6: Right panel Paste notes

**Files:**
- Modify: `partials/right_notes.html`, `app.py`
- Test: `tests/test_ui.py`

**Interfaces:**
- Right panel shows disabled message when no `project_id`
- With project: textarea + Submit `POST /projects/{id}/notes` with `HX-Request`
- Success: return right panel fragment with flash summary; optionally OOB refresh center overview so new data appears

Monkeypatch `build_agent` like current tests.

- [ ] **Step 1: Write failing test**

```python
def test_right_panel_notes_import(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="SWE", start_date="2021"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Ad Blindness"))

    class FakeAgent:
        def __init__(self, *a, **k):
            pass
        def extract_from_notes(self, notes, project_id=None, experience_id=None):
            assert project_id == "p1"
            return {"created": {"contributions": 1}, "updated": {}, "conflicts": []}

    monkeypatch.setattr(ui_app, "build_agent", lambda repo: FakeAgent())
    r = client.post(
        "/projects/p1/notes",
        data={"notes": "I led the ad blindness study."},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert b"Import complete" in r.content or b"created" in r.content.lower()
```

- [ ] **Step 2: Run — expect FAIL** (old redirect-only notes)

- [ ] **Step 3: Implement HTMX notes response**

If `HX-Request`, return `right_notes.html` with message; else redirect to `/` or keep 303 to `/` with query — prefer HTMX path for workspace.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui tests/test_ui.py
git commit -m "feat: right-panel paste notes for scoped Agent 1 import"
```

---

### Task 7: Retire old pages + README + full suite

**Files:**
- Delete unused templates: `experiences.html`, `experience_detail.html`, `project_detail.html`, `open_questions.html` if unused
- Remove dead routes from `app.py`
- Modify: `README.md`
- Modify: `tests/test_ui.py` — ensure no references to deleted pages

- [ ] **Step 1: Update README** — document workspace UI, panels, Edit/Save, paste notes, `--port`

- [ ] **Step 2: Delete old templates/routes; fix any remaining tests**

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/pytest -q`  
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add -A career_agent/ui tests README.md
git commit -m "feat: retire multi-page UI; document career workspace"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Three-panel shell | 2 |
| Search + add experience under search + add project beside org | 3 |
| Experience click ≠ center editor | 3–4 |
| Overview existing fields only | 4 |
| Panel Edit/Save/Cancel | 4–5 |
| Leaf tabs | 5 |
| Paste notes right panel | 6 |
| Leaf deletes for edit removals | 1, 5 |
| README | 7 |
| Phase 2 not built | all |

## Self-review notes

- No TBD placeholders in tasks
- Delete methods named consistently for Task 5
- Old UI tests must be rewritten, not left asserting `/experiences/{id}` pages after Task 7
- HTMX CDN pin `2.0.4` for reproducibility
