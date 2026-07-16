# Project Tree Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Default the left "Experiences" tree to expanded project lists, and add a per-selected-project `⋮` menu with Rename, Duplicate, and Archive actions.

**Architecture:** Server-rendered Jinja partials driven by HTMX, backed by a per-request SQLite `CareerRepository`. Actions POST to new FastAPI routes that mutate the DB and re-render `partials/tree.html`. Duplication is a repository-level deep copy; archiving reuses the existing `Project.status` field and is filtered out of the tree.

**Tech Stack:** Python, FastAPI, Jinja2, HTMX (via CDN), SQLite, pytest + FastAPI `TestClient`.

## Global Constraints

- No new runtime dependencies or libraries (HTMX only, already loaded).
- No DB schema change — reuse the existing `Project.status` field for archiving.
- The dropdown menu uses native `<details>`/`<summary>` — no new JavaScript.
- Archived value is the exact string `"archived"` (lowercase).
- Duplicated project name is `"<original name> (copy)"`, disambiguated with a numeric suffix (`"<name> (copy 2)"`, `"<name> (copy 3)"`, …) when that name already exists within the experience. This is required because a `UNIQUE INDEX ux_projects_match ON projects (experience_id, project_name)` forbids duplicate names within an experience.
- All action routes re-render `partials/tree.html` for HTMX requests and preserve the current search `q` and `selected_project_id` where applicable.
- Run tests with `python -m pytest` from the repo root (`/Users/sarahtxy/dev/career_agent`).

---

### Task 1: Repository `duplicate_project` deep copy

**Files:**
- Modify: `career_agent/repository.py` (imports near top lines 1-22; add method after `update_project` at line 166-167)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: existing `get_project`, `create_project`, `list_contributions`, `create_contribution`, `list_results`, `create_result`, `list_skill_evidence`, `create_skill_evidence`, `list_stories`, `create_story`; `now_iso` (already imported).
- Produces: `CareerRepository.duplicate_project(self, project_id: str) -> Project | None` — creates a new `Project` (new uuid id, a collision-free name derived from `"<name> (copy)"`, `status=None`) plus deep copies of all contributions, results, skill evidence, and stories (new uuid ids, `project_id` pointed at the copy). Returns the new `Project`, or `None` if the source project does not exist. The name must not collide with the unique index `ux_projects_match (experience_id, project_name)`: use `"<name> (copy)"` if free, else `"<name> (copy 2)"`, `"<name> (copy 3)"`, … .

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_repository.py` (top of file already imports `replace`, all models, `CareerRepository`):

```python
def test_duplicate_project_deep_copies_all_leaves(tmp_path):
    repo = make_repository(tmp_path)
    repo.create_contribution(
        Contribution(id="c1", project_id="p1", action="Built pipeline",
                     collaborators=["Ada", "Grace"])
    )
    repo.create_result(
        Result(id="r1", project_id="p1", metric_name="latency", is_estimate=True)
    )
    repo.create_skill_evidence(
        SkillEvidence(id="s1", project_id="p1", skill="Python", independently_used=True)
    )
    repo.create_story(Story(id="st1", project_id="p1", competency="Ownership"))

    copy = repo.duplicate_project("p1")

    assert copy is not None
    assert copy.id != "p1"
    assert copy.project_name == "Platform (copy)"
    assert copy.experience_id == "e1"
    assert copy.status is None
    assert copy.responsibilities == ["design", "delivery"]

    # Original is untouched
    assert len(repo.list_projects("e1")) == 2
    assert len(repo.list_contributions("p1")) == 1

    # Copies exist with new ids pointing at the new project
    copied_contributions = repo.list_contributions(copy.id)
    assert len(copied_contributions) == 1
    assert copied_contributions[0].id != "c1"
    assert copied_contributions[0].action == "Built pipeline"
    assert copied_contributions[0].collaborators == ["Ada", "Grace"]
    assert len(repo.list_results(copy.id)) == 1
    assert repo.list_results(copy.id)[0].is_estimate is True
    assert len(repo.list_skill_evidence(copy.id)) == 1
    assert repo.list_skill_evidence(copy.id)[0].independently_used is True
    assert len(repo.list_stories(copy.id)) == 1


def test_duplicate_project_missing_returns_none(tmp_path):
    repo = make_repository(tmp_path)
    assert repo.duplicate_project("does-not-exist") is None


def test_duplicate_project_disambiguates_repeated_copies(tmp_path):
    repo = make_repository(tmp_path)
    first = repo.duplicate_project("p1")
    second = repo.duplicate_project("p1")
    assert first is not None and second is not None
    names = {p.project_name for p in repo.list_projects("e1")}
    assert names == {"Platform", "Platform (copy)", "Platform (copy 2)"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_repository.py::test_duplicate_project_deep_copies_all_leaves tests/test_repository.py::test_duplicate_project_missing_returns_none -v`
Expected: FAIL with `AttributeError: 'CareerRepository' object has no attribute 'duplicate_project'`

- [ ] **Step 3: Add the `uuid` import and `replace` import**

In `career_agent/repository.py`, update the imports. Change the dataclasses import line (currently line 6):

```python
from dataclasses import asdict, fields, replace
```

Add below the existing `import sqlite3` (near line 5):

```python
import uuid
```

- [ ] **Step 4: Implement `duplicate_project`**

In `career_agent/repository.py`, insert this method immediately after `update_project` (which ends at line 167, before `create_contribution`):

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_repository.py::test_duplicate_project_deep_copies_all_leaves tests/test_repository.py::test_duplicate_project_missing_returns_none -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add career_agent/repository.py tests/test_repository.py
git commit -m "feat(repo): add duplicate_project deep copy"
```

---

### Task 2: Filter archived projects out of the tree

**Files:**
- Modify: `career_agent/ui/app.py` (`_tree_data`, lines 446-474)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: existing `repo.list_projects(experience_id)`.
- Produces: `_tree_data` no longer includes any `Project` whose `status` equals `"archived"` (case-insensitive), in both the no-search and search code paths. Signature unchanged: `_tree_data(repo, q=None) -> tuple[list[Experience], dict[str, list[Project]]]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ui.py` (module already imports `Project`, `Experience`, etc. and has `make_client`):

```python
def test_archived_projects_hidden_from_tree(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Visible One"))
    repo.create_project(
        Project(id="p2", experience_id="e1", project_name="Hidden One", status="archived")
    )

    html = client.get("/partials/tree").text
    assert "Visible One" in html
    assert "Hidden One" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui.py::test_archived_projects_hidden_from_tree -v`
Expected: FAIL — `assert "Hidden One" not in html` fails because the archived project still renders.

- [ ] **Step 3: Add an archive filter helper and apply it in `_tree_data`**

In `career_agent/ui/app.py`, add this helper immediately above `_tree_data` (before line 446):

```python
def _active_projects(projects: list[Project]) -> list[Project]:
    return [
        project
        for project in projects
        if (project.status or "").strip().lower() != "archived"
    ]
```

Then in `_tree_data`, change the initial mapping (currently lines 451-453) from:

```python
    projects_by_experience = {
        experience.id: repo.list_projects(experience.id) for experience in experiences
    }
```

to:

```python
    projects_by_experience = {
        experience.id: _active_projects(repo.list_projects(experience.id))
        for experience in experiences
    }
```

No other change is needed: the search path reads from `projects_by_experience`, so it inherits the filter.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui.py::test_archived_projects_hidden_from_tree -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui/app.py tests/test_ui.py
git commit -m "feat(ui): hide archived projects from the tree"
```

---

### Task 3: Action routes (rename form, rename, duplicate, archive)

**Files:**
- Create: `career_agent/ui/templates/partials/rename_project_form.html`
- Modify: `career_agent/ui/app.py` (add routes inside `create_app`, after the `create_project` route which ends at line 978)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `get_repo()`, `repo.get_project`, `repo.update_project`, `repo.duplicate_project` (Task 1), `_render_tree`, `_is_htmx`, `_redirect`, `replace` (already imported in app.py line 9), `HTTPException`, `Form`.
- Produces four routes:
  - `GET /partials/projects/{project_id}/rename-form?q=&selected_project_id=` → renders `partials/rename_project_form.html`.
  - `POST /projects/{project_id}/rename` (form: `project_name`, `q`, `selected_project_id`) → renames, re-renders tree.
  - `POST /projects/{project_id}/duplicate` (form: `q`, `selected_project_id`) → deep-copies, re-renders tree.
  - `POST /projects/{project_id}/archive` (form: `q`, `selected_project_id`) → sets status `"archived"`, re-renders tree (clearing selection if the archived project was selected).

- [ ] **Step 1: Create the rename form partial**

Create `career_agent/ui/templates/partials/rename_project_form.html`:

```html
<header class="panel-header experiences-header">
  <h1>Rename project</h1>
</header>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form hx-post="/projects/{{ project.id }}/rename" hx-target="#tree-panel">
  <input type="hidden" name="q" value="{{ q | default('') }}">
  <input type="hidden" name="selected_project_id" value="{{ selected_project_id | default('') }}">
  <label>Project name
    <input name="project_name" required value="{{ project.project_name }}">
  </label>
  <button type="submit" class="btn btn-primary">Save</button>
  <button
    type="button"
    class="btn btn-secondary"
    hx-get="/partials/tree?q={{ q | default('') | urlencode }}&selected_project_id={{ selected_project_id | default('') | urlencode }}"
    hx-target="#tree-panel"
  >Cancel</button>
</form>
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_ui.py`:

```python
def _seed_project(db):
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Platform"))
    return repo


def test_rename_form_partial_prefills_name(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    _seed_project(db)
    r = client.get("/partials/projects/p1/rename-form?selected_project_id=p1")
    assert r.status_code == 200
    assert 'value="Platform"' in r.text
    assert "/projects/p1/rename" in r.text


def test_rename_project_updates_name(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    _seed_project(db)
    r = client.post(
        "/projects/p1/rename",
        data={"project_name": "Renamed Platform", "selected_project_id": "p1"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Renamed Platform" in r.text
    assert CareerRepository(db).get_project("p1").project_name == "Renamed Platform"


def test_rename_project_blank_is_rejected(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    _seed_project(db)
    r = client.post(
        "/projects/p1/rename",
        data={"project_name": "   ", "selected_project_id": "p1"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 400
    assert CareerRepository(db).get_project("p1").project_name == "Platform"


def test_duplicate_project_route_adds_copy(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    _seed_project(db)
    r = client.post(
        "/projects/p1/duplicate",
        data={"selected_project_id": "p1"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Platform (copy)" in r.text
    assert len(CareerRepository(db).list_projects("e1")) == 2


def test_archive_project_route_hides_project(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    _seed_project(db)
    r = client.post(
        "/projects/p1/archive",
        data={"selected_project_id": "p1"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Platform" not in r.text
    assert CareerRepository(db).get_project("p1").status == "archived"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_ui.py -k "rename or duplicate_project_route or archive_project_route" -v`
Expected: FAIL — rename-form/rename/duplicate/archive routes return 404/405 (not yet defined).

- [ ] **Step 4: Add the routes**

In `career_agent/ui/app.py`, inside `create_app`, add the following immediately after the `create_project` route (after line 978, before the `/projects/{project_id}/notes` route):

```python
    @app.get("/partials/projects/{project_id}/rename-form")
    def partial_rename_project(
        request: Request,
        project_id: str,
        q: str = "",
        selected_project_id: str = "",
    ):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return templates.TemplateResponse(
            request,
            "partials/rename_project_form.html",
            {
                "project": project,
                "q": q,
                "selected_project_id": selected_project_id or project_id,
            },
        )

    @app.post("/projects/{project_id}/rename")
    def rename_project(
        request: Request,
        project_id: str,
        project_name: str = Form(...),
        q: str = Form(""),
        selected_project_id: str = Form(""),
    ):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        name = project_name.strip()
        if not name:
            return templates.TemplateResponse(
                request,
                "partials/rename_project_form.html",
                {
                    "project": project,
                    "q": q,
                    "selected_project_id": selected_project_id or project_id,
                    "error": "Project name is required.",
                },
                status_code=400,
            )
        repo.update_project(replace(project, project_name=name))
        if _is_htmx(request):
            return _render_tree(
                request,
                repo,
                q=q or None,
                selected_project_id=selected_project_id or project_id,
            )
        return _redirect("/", flash=f"Renamed project: {name}")

    @app.post("/projects/{project_id}/duplicate")
    def duplicate_project(
        request: Request,
        project_id: str,
        q: str = Form(""),
        selected_project_id: str = Form(""),
    ):
        repo = get_repo()
        new_project = repo.duplicate_project(project_id)
        if new_project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if _is_htmx(request):
            return _render_tree(
                request,
                repo,
                q=q or None,
                selected_project_id=selected_project_id or None,
            )
        return _redirect("/", flash=f"Duplicated project: {new_project.project_name}")

    @app.post("/projects/{project_id}/archive")
    def archive_project(
        request: Request,
        project_id: str,
        q: str = Form(""),
        selected_project_id: str = Form(""),
    ):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        repo.update_project(replace(project, status="archived"))
        new_selected = "" if selected_project_id == project_id else selected_project_id
        if _is_htmx(request):
            return _render_tree(
                request,
                repo,
                q=q or None,
                selected_project_id=new_selected or None,
            )
        return _redirect("/", flash=f"Archived project: {project.project_name}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ui.py -k "rename or duplicate_project_route or archive_project_route" -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add career_agent/ui/app.py career_agent/ui/templates/partials/rename_project_form.html tests/test_ui.py
git commit -m "feat(ui): add rename, duplicate, and archive project routes"
```

---

### Task 4: Tree template — expand by default + `⋮` action menu + styles

**Files:**
- Modify: `career_agent/ui/templates/partials/tree.html` (lines 32-49)
- Modify: `career_agent/ui/templates/workspace.html` (`<style>` block; add rules near `.tree-project` at lines 89-98)
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: template vars already passed by `_render_tree` / `_tree_template_context`: `experiences`, `projects_by_experience`, `selected_project_id`, `q`. Routes from Task 3.
- Produces: each experience `<details>` renders `open`; the selected project row renders a `<details class="proj-menu">` dropdown containing Rename/Duplicate/Archive controls wired to the Task 3 routes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ui.py`:

```python
def test_tree_details_open_by_default(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    _seed_project(db)
    html = client.get("/partials/tree").text
    assert "<details open>" in html


def test_selected_project_shows_action_menu(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    _seed_project(db)
    selected = client.get("/partials/tree?selected_project_id=p1").text
    assert "proj-menu" in selected
    assert "Rename" in selected
    assert "Duplicate" in selected
    assert "Archive" in selected

    unselected = client.get("/partials/tree").text
    assert "proj-menu" not in unselected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ui.py -k "details_open or action_menu" -v`
Expected: FAIL — `<details open>` is conditional today, and `proj-menu` markup does not exist yet.

- [ ] **Step 3: Update `tree.html` — always-open details and the project menu**

In `career_agent/ui/templates/partials/tree.html`, change the `<details>` opening tag (currently line 32):

```html
            <details{% if experience_projects | selectattr("id", "equalto", selected_project_id) | list %} open{% endif %}>
```

to:

```html
            <details open>
```

Then replace the project loop body (currently lines 39-49):

```html
                  {% for project in experience_projects %}
                    <li>
                      <a
                        href="#"
                        class="tree-project{% if selected_project_id == project.id %} is-selected{% endif %}"
                        hx-get="/partials/projects/{{ project.id }}?tab=overview"
                        hx-target="#center-panel"
                        hx-include="[name='q']"
                      >{{ project.project_name }}</a>
                    </li>
                  {% endfor %}
```

with:

```html
                  {% for project in experience_projects %}
                    <li class="tree-project-row">
                      <a
                        href="#"
                        class="tree-project{% if selected_project_id == project.id %} is-selected{% endif %}"
                        hx-get="/partials/projects/{{ project.id }}?tab=overview"
                        hx-target="#center-panel"
                        hx-include="[name='q']"
                      >{{ project.project_name }}</a>
                      {% if selected_project_id == project.id %}
                        <details class="proj-menu">
                          <summary class="proj-menu-toggle" aria-label="Project actions">⋮</summary>
                          <div class="proj-menu-list">
                            <button
                              type="button"
                              class="proj-menu-item"
                              hx-get="/partials/projects/{{ project.id }}/rename-form"
                              hx-target="#tree-panel"
                              hx-include="[name='q'], [name='selected_project_id']"
                            >Rename</button>
                            <button
                              type="button"
                              class="proj-menu-item"
                              hx-post="/projects/{{ project.id }}/duplicate"
                              hx-target="#tree-panel"
                              hx-include="[name='q'], [name='selected_project_id']"
                            >Duplicate</button>
                            <button
                              type="button"
                              class="proj-menu-item"
                              hx-post="/projects/{{ project.id }}/archive"
                              hx-target="#tree-panel"
                              hx-include="[name='q'], [name='selected_project_id']"
                              hx-confirm="Archive this project? It will be hidden from the tree."
                            >Archive</button>
                          </div>
                        </details>
                      {% endif %}
                    </li>
                  {% endfor %}
```

Note: the hidden `selected_project_id` input already present in `tree.html` (line 23) carries the current selection, and the search `q` input is also in `tree.html`. `hx-include="[name='q'], [name='selected_project_id']"` forwards both to every action, so the routes receive them as form fields (matching the `Form("")` params from Task 3). No values are placed in the URL query string.

- [ ] **Step 4: Add dropdown styles to `workspace.html`**

In `career_agent/ui/templates/workspace.html`, immediately after the `.tree-project.is-selected { ... }` rule (ends at line 98), add:

```css
    .tree-project-row {
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }
    .tree-project-row .tree-project { flex: 1; min-width: 0; }
    .proj-menu { position: relative; flex-shrink: 0; }
    .proj-menu > summary {
      list-style: none;
      cursor: pointer;
      padding: 0.1rem 0.4rem;
      border-radius: var(--radius);
      color: var(--text-muted);
      user-select: none;
      line-height: 1;
    }
    .proj-menu > summary::-webkit-details-marker { display: none; }
    .proj-menu > summary::marker { content: ""; }
    .proj-menu[open] > summary { background: var(--accent-soft); }
    .proj-menu-list {
      position: absolute;
      right: 0;
      top: 100%;
      z-index: 10;
      margin-top: 2px;
      min-width: 140px;
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
      padding: 0.25rem;
      display: flex;
      flex-direction: column;
    }
    .proj-menu-item {
      display: block;
      width: 100%;
      text-align: left;
      margin-top: 0;
      border: none;
      background: none;
      padding: 0.35rem 0.5rem;
      border-radius: var(--radius);
      cursor: pointer;
      font-size: 0.85rem;
      color: var(--text);
    }
    .proj-menu-item:hover { background: var(--accent-soft); }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ui.py -k "details_open or action_menu" -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest`
Expected: PASS (all tests, including pre-existing ones)

- [ ] **Step 7: Commit**

```bash
git add career_agent/ui/templates/partials/tree.html career_agent/ui/templates/workspace.html tests/test_ui.py
git commit -m "feat(ui): expand tree by default and add selected-project action menu"
```

---

## Self-Review

**Spec coverage:**
- Expand-by-default → Task 4 (`<details open>`), tested by `test_tree_details_open_by_default`.
- `⋮` menu on selected project only → Task 4, tested by `test_selected_project_shows_action_menu`.
- Rename → Task 3 routes + Task 4 markup, tested by `test_rename_form_partial_prefills_name`, `test_rename_project_updates_name`, `test_rename_project_blank_is_rejected`.
- Duplicate (deep copy) → Task 1 repo + Task 3 route, tested by repo deep-copy test and `test_duplicate_project_route_adds_copy`.
- Archive (hide, keep in DB, `status="archived"`, confirm) → Task 2 filter + Task 3 route + Task 4 `hx-confirm`, tested by `test_archived_projects_hidden_from_tree` and `test_archive_project_route_hides_project`.
- No schema change / no new deps / native `<details>` dropdown → honored across tasks.
- Restore/unarchive UI → intentionally out of scope (spec).

**Placeholder scan:** No TBD/TODO; all steps include concrete code and exact commands.

**Type consistency:** `duplicate_project(project_id: str) -> Project | None` defined in Task 1 and consumed in Task 3. Route form params (`project_name`, `q`, `selected_project_id`) match the template's `hx-include`/hidden inputs. `_active_projects(list[Project]) -> list[Project]` defined and used only in Task 2. Archive value `"archived"` consistent between route (write) and `_active_projects` (filter).
