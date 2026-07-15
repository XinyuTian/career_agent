# Career Workspace Visual Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the existing three-panel HTMX career workspace to match the approved mockup (tokens, typography, light layout hierarchy) without changing Edit/gap/notes behavior.

**Architecture:** Keep styles and design tokens in `workspace.html`. Light Jinja markup tweaks for Experiences header, org/role/project tree, status badge, pill tabs, and completeness progress bar. Pass optional `selected_project_id` through tree renders (and OOB-refresh the tree when a project loads) so the active project chip persists. No schema or completeness-rule changes.

**Tech Stack:** FastAPI, Jinja2, HTMX, pytest + TestClient, Inter via Google Fonts CDN.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-14-career-workspace-visual-restyle-design.md`
- CSS stays in `workspace.html` (no separate CSS file, no Tailwind)
- Keep panel-level Edit / Save / Cancel
- Keep hover/focus gap actions (Answer now / Mark as unknown)
- No Continue interview CTA
- No new Overview fields / Methods tags
- Gap list heading label: **Needs clarification**
- Left header label: **Experiences**; search placeholder: **Search**
- Selected project uses soft accent background class `tree-project.is-selected`

---

## File map

| File | Responsibility |
|------|----------------|
| `career_agent/ui/templates/workspace.html` | Design tokens, Inter, panel/button/tab/progress CSS |
| `career_agent/ui/templates/partials/tree.html` | Experiences header, hierarchy markup, selected class, hidden selected id |
| `career_agent/ui/templates/partials/center_tabs.html` | Soft pill tabs |
| `career_agent/ui/templates/partials/center_overview_inner.html` | Title, status badge, subtitle, panel Edit, section layout |
| `career_agent/ui/templates/partials/center_overview_edit.html` | Matching header + primary/secondary buttons |
| `career_agent/ui/templates/partials/center_leaves_read.html` / `center_leaves_edit.html` / `center_leaves_inner.html` | Button/header class alignment |
| `career_agent/ui/templates/partials/center_overview_read.html` / `center_leaves_read.html` | OOB tree refresh with selected project |
| `career_agent/ui/templates/partials/completeness.html` | Progress bar + Needs clarification heading |
| `career_agent/ui/templates/partials/right_notes.html` | Secondary/primary button classes |
| `career_agent/ui/app.py` | `selected_project_id` on tree render; pass tree ctx into project reads |
| `tests/test_ui.py` | Copy/selection/CSS-hook assertions |

---

### Task 1: Selected project highlight plumbing

**Files:**
- Modify: `career_agent/ui/app.py` (`_render_tree`, `partial_tree`, `_render_overview_read`, `_render_leaves_read`, `home` if needed)
- Modify: `career_agent/ui/templates/partials/tree.html`
- Modify: `career_agent/ui/templates/partials/center_overview_read.html`
- Modify: `career_agent/ui/templates/partials/center_leaves_read.html`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `_tree_data(repo, q)`, existing project partial renderers
- Produces:
  - `_render_tree(request, repo, *, q: str | None = None, selected_project_id: str | None = None) -> Any`
  - Template context always includes `selected_project_id` (string, maybe empty)
  - `GET /partials/tree?q=&selected_project_id=` preserves selection through search
  - Overview/leaves read responses OOB-swap `#tree-panel` with tree for that project

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ui.py`:

```python
def test_tree_marks_selected_project(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))
    repo.create_project(Project(id="p2", experience_id="e1", project_name="Ads"))

    r = client.get("/partials/tree?selected_project_id=p1")
    assert r.status_code == 200
    assert b'class="tree-project is-selected"' in r.content or b"tree-project is-selected" in r.content
    assert b"Search" in r.content


def test_project_overview_oob_selects_tree_project(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Acme", title="SWE"))
    repo.create_project(Project(id="p1", experience_id="e1", project_name="Search"))

    r = client.get("/partials/projects/p1?tab=overview")
    assert r.status_code == 200
    assert b'id="tree-panel"' in r.content
    assert b"hx-swap-oob" in r.content
    assert b"tree-project is-selected" in r.content
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `.venv/bin/pytest tests/test_ui.py::test_tree_marks_selected_project tests/test_ui.py::test_project_overview_oob_selects_tree_project -v`  
Expected: FAIL (selected class / OOB tree missing)

- [ ] **Step 3: Update `_render_tree` and `partial_tree`**

In `career_agent/ui/app.py`:

```python
def _render_tree(
    request: Request,
    repo: CareerRepository,
    *,
    q: str | None = None,
    selected_project_id: str | None = None,
) -> Any:
    experiences, projects_by_experience = _tree_data(repo, q)
    return templates.TemplateResponse(
        request,
        "partials/tree.html",
        {
            "experiences": experiences,
            "projects_by_experience": projects_by_experience,
            "q": q or "",
            "selected_project_id": selected_project_id or "",
        },
    )
```

```python
@app.get("/partials/tree")
def partial_tree(
    request: Request,
    q: str = "",
    selected_project_id: str = "",
):
    return _render_tree(
        request,
        get_repo(),
        q=q or None,
        selected_project_id=selected_project_id or None,
    )
```

- [ ] **Step 4: Pass tree context from project reads + OOB partial**

Add helper near `_render_tree`:

```python
def _tree_template_context(
    repo: CareerRepository,
    *,
    q: str | None = None,
    selected_project_id: str | None = None,
) -> dict[str, Any]:
    experiences, projects_by_experience = _tree_data(repo, q)
    return {
        "experiences": experiences,
        "projects_by_experience": projects_by_experience,
        "q": q or "",
        "selected_project_id": selected_project_id or "",
    }
```

Update `_render_overview_read` and `_render_leaves_read` context to include `**_tree_template_context(repo, selected_project_id=project_id)`.

At the bottom of `center_overview_read.html` and `center_leaves_read.html` (alongside existing right-panel OOB), add:

```html
<aside id="tree-panel" hx-swap-oob="true">
  {% include "partials/tree.html" %}
</aside>
```

- [ ] **Step 5: Update `tree.html` for selection + preserve on search**

Replace the search block so it includes a hidden selected id and marks the active project:

```html
<header class="panel-header experiences-header">
  <h1>Experiences</h1>
  <button
    type="button"
    class="btn btn-secondary"
    hx-get="/partials/add-experience"
    hx-target="#tree-panel"
  >+ Add</button>
</header>
<label class="search">
  <span class="sr-only">Search</span>
  <input
    type="search"
    name="q"
    placeholder="Search"
    value="{{ q | default('') }}"
    hx-get="/partials/tree"
    hx-trigger="keyup changed delay:200ms"
    hx-target="#tree-panel"
    hx-include="[name='selected_project_id']"
  >
</label>
<input type="hidden" name="selected_project_id" value="{{ selected_project_id | default('') }}">
```

For each project link:

```html
<li>
  <a
    href="#"
    class="tree-project{% if selected_project_id == project.id %} is-selected{% endif %}"
    hx-get="/partials/projects/{{ project.id }}?tab=overview"
    hx-target="#center-panel"
  >{{ project.project_name }}</a>
</li>
```

Also split organization vs role in the summary (org bold line, title muted). Keep `+ Add project` button with `class="btn btn-secondary"`. Update Cancel links in add forms later tasks if needed — for this task, `hx-get="/partials/tree"` cancels lose selection (acceptable); optional: append `?selected_project_id={{ selected_project_id }}` when available on cancel buttons in Task 2.

Ensure `home` TemplateResponse passes `"selected_project_id": ""` so includes do not break.

- [ ] **Step 6: Run tests — expect PASS**

Run: `.venv/bin/pytest tests/test_ui.py::test_tree_marks_selected_project tests/test_ui.py::test_project_overview_oob_selects_tree_project -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add career_agent/ui/app.py career_agent/ui/templates/partials/tree.html \
  career_agent/ui/templates/partials/center_overview_read.html \
  career_agent/ui/templates/partials/center_leaves_read.html \
  tests/test_ui.py
git commit -m "$(cat <<'EOF'
feat: highlight selected project in workspace tree

Pass selected_project_id through tree partials and OOB-refresh the navigator when a project loads.
EOF
)"
```

---

### Task 2: Design tokens and shell CSS

**Files:**
- Modify: `career_agent/ui/templates/workspace.html`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: existing `#tree-panel`, `#center-panel`, `#right-panel` shell
- Produces: CSS variables and shared utility classes used by later template tasks:
  - `.btn`, `.btn-primary`, `.btn-secondary`
  - `.tab`, `.tab.is-active`
  - `.badge`, `.progress`, `.progress__bar`
  - `.overview-section`, `.tree-project.is-selected`

- [ ] **Step 1: Write the failing test**

```python
def test_workspace_shell_includes_design_tokens(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b"--accent:" in r.content
    assert b"btn-primary" in r.content or b"--bg-panel" in r.content
    assert b"fonts.googleapis.com" in r.content or b"Inter" in r.content
```

(After CSS lands, `--accent` and Inter link will pass; `btn-primary` may only appear once partials use it — assert tokens/font in this task.)

Prefer:

```python
def test_workspace_shell_includes_design_tokens(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200
    assert b"--accent:" in r.content
    assert b"--bg-panel:" in r.content
    assert b"Inter" in r.content
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `.venv/bin/pytest tests/test_ui.py::test_workspace_shell_includes_design_tokens -v`  
Expected: FAIL (`--accent` missing)

- [ ] **Step 3: Replace shell styles in `workspace.html`**

In `<head>`, add:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

Replace the `<style>` block with token-driven CSS (keep existing functional rules for `.sr-only`, gap hover, flash, forms). Core tokens:

```css
:root {
  --bg-page: #F3F4F6;
  --bg-panel: #FFFFFF;
  --border: #E5E7EB;
  --text: #111827;
  --text-muted: #6B7280;
  --accent: #3B82F6;
  --accent-soft: #EFF6FF;
  --accent-text: #1D4ED8;
  --radius: 10px;
  color-scheme: light;
}
body {
  margin: 0;
  font-family: Inter, system-ui, -apple-system, sans-serif;
  line-height: 1.45;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-page);
  color: var(--text);
}
.workspace {
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  gap: 12px;
  height: 100vh;
  padding: 12px;
}
#tree-panel,
#center-panel,
#right-panel {
  overflow-y: auto;
  padding: 24px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 0;
  padding: 0.45rem 0.85rem;
  border-radius: var(--radius);
  font-family: inherit;
  font-size: 0.9rem;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent);
  color: #fff;
  border: 1px solid var(--accent);
}
.btn-secondary {
  background: #fff;
  color: var(--text);
  border: 1px solid var(--border);
}
.tree-project {
  display: block;
  padding: 0.35rem 0.6rem;
  border-radius: var(--radius);
  color: var(--text);
  text-decoration: none;
}
.tree-project.is-selected {
  background: var(--accent-soft);
}
.tab {
  display: inline-block;
  padding: 0.35rem 0.75rem;
  border-radius: var(--radius);
  color: var(--text-muted);
  text-decoration: none;
}
.tab.is-active {
  background: var(--accent-soft);
  color: var(--accent-text);
  font-weight: 600;
}
.badge {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-text);
  font-size: 0.8rem;
  font-weight: 500;
}
.progress {
  height: 8px;
  background: #E5E7EB;
  border-radius: 999px;
  overflow: hidden;
  margin: 0.5rem 0 1rem;
}
.progress__bar {
  height: 100%;
  background: var(--accent);
  border-radius: 999px;
}
.muted { color: var(--text-muted); font-style: normal; }
```

Preserve `.gap-actions` hover/focus-within opacity behavior from the current file. Style `input`, `textarea`, `button` defaults to match radius/border. Update `#center-panel` so it is white like the mockup (drop gray wash).

- [ ] **Step 4: Run test — expect PASS**

Run: `.venv/bin/pytest tests/test_ui.py::test_workspace_shell_includes_design_tokens -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui/templates/workspace.html tests/test_ui.py
git commit -m "$(cat <<'EOF'
style: add workspace design tokens and Inter typography

Replace monospace shell styles with mockup-aligned colors, buttons, tabs, and progress bar primitives.
EOF
)"
```

---

### Task 3: Left panel copy and hierarchy polish

**Files:**
- Modify: `career_agent/ui/templates/partials/tree.html`
- Modify: `career_agent/ui/templates/partials/add_experience_form.html`
- Modify: `career_agent/ui/templates/partials/add_project_form.html`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `selected_project_id` from Task 1; `.btn-secondary` from Task 2
- Produces: Experiences header UX; org/role/project hierarchy classes `.tree-org`, `.tree-role`

- [ ] **Step 1: Update failing copy assertions**

In `test_home_lists_experiences`, replace:

```python
assert b"Career navigator" in r.content
assert b"Search experiences and projects" in r.content
```

with:

```python
assert b"Experiences" in r.content
assert b'placeholder="Search"' in r.content
assert b"+ Add" in r.content
```

- [ ] **Step 2: Run test — expect FAIL if tree still says Career navigator**

Run: `.venv/bin/pytest tests/test_ui.py::test_home_lists_experiences -v`  
If Task 1 already changed header to Experiences, this may already PASS — continue polish anyway.

- [ ] **Step 3: Finish tree hierarchy markup**

Inside each experience `<details>` summary:

```html
<summary>
  <span class="tree-org">{{ experience.organization }}</span>
  <span class="tree-role">{{ experience.title }}</span>
</summary>
```

Add CSS in `workspace.html` if not already present:

```css
.experiences-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.experiences-header h1 {
  margin: 0;
  font-size: 1.1rem;
}
.tree-org { display: block; font-weight: 600; }
.tree-role {
  display: block;
  color: var(--text-muted);
  font-size: 0.85rem;
  margin: 0.15rem 0 0.35rem;
}
```

Ensure add forms Cancel buttons use `class="btn btn-secondary"` and primary submit uses `class="btn btn-primary"`. Prefer cancel URLs:

```html
hx-get="/partials/tree?selected_project_id={{ selected_project_id | default('') }}"
```

(Pass `selected_project_id` into add-experience/add-project template contexts from their routes — empty string default is fine.)

- [ ] **Step 4: Run UI home + tree tests**

Run: `.venv/bin/pytest tests/test_ui.py::test_home_lists_experiences tests/test_ui.py::test_tree_marks_selected_project -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui/templates/partials/tree.html \
  career_agent/ui/templates/partials/add_experience_form.html \
  career_agent/ui/templates/partials/add_project_form.html \
  career_agent/ui/templates/workspace.html \
  career_agent/ui/app.py \
  tests/test_ui.py
git commit -m "$(cat <<'EOF'
style: restyle experiences navigator to match mockup

Use Experiences/+ Add header, Search placeholder, and org/role/project hierarchy.
EOF
)"
```

---

### Task 4: Center panel restyle

**Files:**
- Modify: `career_agent/ui/templates/partials/center_tabs.html`
- Modify: `career_agent/ui/templates/partials/center_overview_inner.html`
- Modify: `career_agent/ui/templates/partials/center_overview_edit.html`
- Modify: `career_agent/ui/templates/partials/center_leaves_inner.html` (if present) / leaves read+edit templates
- Modify: `career_agent/ui/templates/partials/center_placeholder.html`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `.tab`, `.badge`, `.btn-primary`, `.btn-secondary`
- Produces: status badge when `project.status` set; subtitle `Organization · Title`; pill tabs; panel Edit as primary button

- [ ] **Step 1: Write the failing test**

```python
def test_overview_header_shows_status_badge_and_subtitle(tmp_path, monkeypatch):
    client, db = make_client(tmp_path, monkeypatch)
    repo = CareerRepository(db)
    repo.create_experience(Experience(id="e1", organization="Google", title="Research Data Scientist"))
    repo.create_project(
        Project(
            id="p1",
            experience_id="e1",
            project_name="Ad Blindness",
            status="In progress",
        )
    )
    r = client.get("/partials/projects/p1?tab=overview")
    assert r.status_code == 200
    assert b"Ad Blindness" in r.content
    assert b"badge" in r.content
    assert b"In progress" in r.content
    assert b"Google" in r.content
    assert b"Research Data Scientist" in r.content
    assert b"class=\"tab is-active\"" in r.content or b"tab is-active" in r.content
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `.venv/bin/pytest tests/test_ui.py::test_overview_header_shows_status_badge_and_subtitle -v`  
Expected: FAIL (badge / tab classes missing)

- [ ] **Step 3: Update tabs**

`center_tabs.html`:

```html
<nav class="center-tabs" aria-label="Project tabs">
  {% set tabs = [
    ('overview', 'Overview'),
    ('contributions', 'Contributions'),
    ('results', 'Results'),
    ('skills', 'Skills'),
    ('stories', 'Stories'),
  ] %}
  {% for tab_id, tab_label in tabs %}
    {% if active_tab == tab_id %}
      <span class="tab is-active">{{ tab_label }}</span>
    {% else %}
      <a
        class="tab"
        href="#"
        hx-get="/partials/projects/{{ project.id }}?tab={{ tab_id }}"
        hx-target="#center-panel"
      >{{ tab_label }}</a>
    {% endif %}
  {% endfor %}
</nav>
```

- [ ] **Step 4: Update overview read header + sections**

In `center_overview_inner.html` header:

```html
<header class="panel-header project-header">
  <div class="project-title-row">
    <h2>{{ project.project_name }}</h2>
    {% if project.status %}
      <span class="badge">{{ project.status }}</span>
    {% endif %}
  </div>
  <p class="muted">{{ experience.organization }} · {{ experience.title }}</p>
</header>
```

Replace dl/dt layout with sections (same fields/values):

```html
<section class="overview-read">
  <div class="overview-actions">
    <button
      type="button"
      class="btn btn-primary"
      hx-get="/partials/projects/{{ project.id }}/edit?tab=overview"
      hx-target="#center-panel"
    >Edit</button>
  </div>

  <div class="overview-section">
    <h3>Problem</h3>
    <p>{% if project.problem %}{{ project.problem }}{% else %}<span class="muted">Not set yet</span>{% endif %}</p>
  </div>
  <div class="overview-section">
    <h3>Business context</h3>
    <p>{% if project.business_context %}{{ project.business_context }}{% else %}<span class="muted">Not set yet</span>{% endif %}</p>
  </div>
  <div class="overview-section">
    <h3>Your role</h3>
    <p>{% if project.personal_role %}{{ project.personal_role }}{% else %}<span class="muted">Not set yet</span>{% endif %}</p>
  </div>
  <div class="overview-section">
    <h3>Stakeholders</h3>
    <p>{% if project.users_or_stakeholders %}{{ project.users_or_stakeholders }}{% else %}<span class="muted">Not set yet</span>{% endif %}</p>
  </div>
  <div class="overview-section">
    <h3>Responsibilities</h3>
    {% if project.responsibilities %}
      <ul>
        {% for item in project.responsibilities %}
          <li>{{ item }}</li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="muted">Not set yet</p>
    {% endif %}
  </div>
  <div class="overview-section">
    <h3>Stage</h3>
    <p>{% if project.project_stage %}{{ project.project_stage }}{% else %}<span class="muted">Not set yet</span>{% endif %}</p>
  </div>
  <div class="overview-section">
    <h3>Timeline</h3>
    <p>{% if project.timeline %}{{ project.timeline }}{% else %}<span class="muted">Not set yet</span>{% endif %}</p>
  </div>
  <div class="overview-section">
    <h3>Status</h3>
    <p>{% if project.status %}{{ project.status }}{% else %}<span class="muted">Not set yet</span>{% endif %}</p>
  </div>
</section>
```

Do **not** add Methods tags.

Mirror header subtitle/badge on `center_overview_edit.html`; Save = `btn btn-primary`, Cancel = `btn btn-secondary`.

Apply the same button classes on leaves Edit/Save/Cancel controls.

- [ ] **Step 5: Run tests — expect PASS**

Run: `.venv/bin/pytest tests/test_ui.py::test_overview_header_shows_status_badge_and_subtitle tests/test_ui.py::test_project_tabs_show_leaf_sections -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add career_agent/ui/templates/partials/center_*.html tests/test_ui.py career_agent/ui/templates/workspace.html
git commit -m "$(cat <<'EOF'
style: restyle project workspace header, tabs, and overview

Add status badge, accent pill tabs, and panel Edit primary styling.
EOF
)"
```

---

### Task 5: Right panel completeness + notes restyle

**Files:**
- Modify: `career_agent/ui/templates/partials/completeness.html`
- Modify: `career_agent/ui/templates/partials/right_notes.html`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `.progress`, `.progress__bar`, `.btn-secondary`, `.btn-primary`
- Produces: Completeness row with percent + bar; heading **Needs clarification**; restyled Paste notes

- [ ] **Step 1: Update / add assertions**

Update `test_right_panel_shows_completeness`:

```python
assert b"Completeness" in r.content
assert b"Needs clarification" in r.content
assert b"progress__bar" in r.content
assert b"Paste notes" in r.content
assert b"Continue interview" not in r.content
```

(Keep existing gap text assertion softer / still valid.)

- [ ] **Step 2: Run test — expect FAIL**

Run: `.venv/bin/pytest tests/test_ui.py::test_right_panel_shows_completeness -v`  
Expected: FAIL (`Needs clarification` / progress bar missing)

- [ ] **Step 3: Update `completeness.html`**

```html
<section class="completeness-block">
  <div class="completeness-row">
    <h3 class="completeness-heading">Completeness</h3>
    <span class="completeness-percent">{{ completeness.percent }}%</span>
  </div>
  <div class="progress" aria-hidden="true">
    <div class="progress__bar" style="width: {{ completeness.percent }}%"></div>
  </div>
  <h3 class="completeness-heading">Needs clarification</h3>
  {% if completeness.missing %}
    <ul class="gap-list">
      {% for gap in completeness.missing %}
        <li class="gap-row">
          <span class="gap-label">{{ gap.label }}</span>
          <span class="gap-actions">
            <button type="button" class="btn btn-secondary gap-action"
              hx-get="/projects/{{ project.id }}/gaps/answer-form"
              hx-vals='{"gap_key": "{{ gap.key }}"}'
              hx-target="#right-panel"
            >Answer now</button>
            <button type="button" class="btn btn-secondary gap-action"
              hx-post="/projects/{{ project.id }}/gaps/unknown"
              hx-vals='{"gap_key": "{{ gap.key }}"}'
              hx-target="#right-panel"
            >Mark as unknown</button>
          </span>
          {% if expanded_gap_key == gap.key %}
            <!-- keep existing answer form markup; style submit with btn-primary -->
            <form class="gap-answer-form" hx-post="/projects/{{ project.id }}/gaps/answer" hx-target="#right-panel">
              <input type="hidden" name="gap_key" value="{{ gap.key }}">
              <label>
                Answer
                <textarea name="answer" rows="3" required></textarea>
              </label>
              <button type="submit" class="btn btn-primary gap-action">Submit</button>
              <button
                type="button"
                class="btn btn-secondary gap-action"
                hx-get="/projects/{{ project.id }}/gaps/answer-form?gap_key={{ gap.key }}&cancel=true"
                hx-target="#right-panel"
              >Cancel</button>
            </form>
          {% endif %}
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="muted">Nothing missing — great work.</p>
  {% endif %}
</section>
<hr class="panel-divider">
```

Keep `.gap-actions` CSS opacity:0 until hover/focus-within.

Add:

```css
.completeness-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}
.completeness-heading {
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  text-transform: none;
  letter-spacing: normal;
}
.completeness-percent { font-weight: 600; color: var(--text); }
```

In `right_notes.html`, give Import notes `class="btn btn-primary"`; leave disabled state as today.

- [ ] **Step 4: Run tests — expect PASS**

Run: `.venv/bin/pytest tests/test_ui.py::test_right_panel_shows_completeness tests/test_ui.py::test_mark_unknown_dismisses_overview_gap -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add career_agent/ui/templates/partials/completeness.html \
  career_agent/ui/templates/partials/right_notes.html \
  career_agent/ui/templates/workspace.html \
  tests/test_ui.py
git commit -m "$(cat <<'EOF'
style: restyle completeness panel to match mockup

Add progress bar, Needs clarification heading, and primary/secondary button classes.
EOF
)"
```

---

### Task 6: Full regression pass

**Files:**
- Modify: `tests/test_ui.py` only if any remaining old-copy assertions fail
- Verify: full suite

**Interfaces:**
- Consumes: Tasks 1–5 complete UI
- Produces: green suite; no interviewer CTA; no intentional behavior regressions

- [ ] **Step 1: Run full UI tests**

Run: `.venv/bin/pytest tests/test_ui.py -v`  
Expected: PASS  
Fix any leftover assertions still looking for `Career navigator`, `Project completeness:`, pipe-separated tabs, or `Missing` heading.

- [ ] **Step 2: Run full suite**

Run: `.venv/bin/pytest -v`  
Expected: PASS (same count as before restyle ± new tests added)

- [ ] **Step 3: Manual smoke checklist**

Start UI (`career-agent ui` or project’s documented command), then verify:

1. Left: Experiences, Search, org/role/projects, selected project soft blue
2. Center: badge, subtitle middle-dot, pill Overview tab, Edit primary
3. Right: Completeness % + bar, Needs clarification, hover Answer now, Paste notes — **no** Continue interview

- [ ] **Step 4: Commit only if Step 1 required assertion fixes**

```bash
git add tests/test_ui.py
git commit -m "$(cat <<'EOF'
test: align UI assertions with visual restyle copy

EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Tokens / Inter / colors | Task 2 |
| Panel surfaces, radius, padding | Task 2 |
| Experiences + Add + Search | Tasks 1/3 |
| Org / role / project hierarchy | Task 3 |
| Selected project soft blue | Task 1 |
| Status badge + `Org · Title` | Task 4 |
| Pill tabs | Task 4 |
| Panel-level Edit styling | Task 4 |
| Completeness progress bar | Task 5 |
| Needs clarification label | Task 5 |
| Hover gap actions preserved | Task 5 |
| No Continue interview | Task 5 assertion |
| No Methods tags / schema changes | Task 4 (explicit non-add) |
| CSS in workspace.html only | Task 2 |
| pytest + HTMX smoke | Task 6 |
