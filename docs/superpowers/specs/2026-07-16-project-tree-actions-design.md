# Project Tree: Expanded Default + Per-Project Actions

Date: 2026-07-16
Status: Approved for planning (pending final user review of this doc)
Depends on: Career workspace UI (`2026-07-14-career-workspace-ui-design.md`)

## Goal

Two changes to the left "Experiences" tree panel:

1. Each experience's project list is **expanded by default** on load (currently collapsed unless it contains the selected project).
2. When a project is **selected**, a three-dots (`⋮`) menu appears at the right of the project name, exposing three actions: **Rename**, **Duplicate**, **Archive**.

## Decisions

| Topic | Choice |
|-------|--------|
| Expand default | Experience `<details>` always renders `open` |
| Menu trigger | `⋮` button, shown only on the selected project row |
| Menu style | Small dropdown popover anchored under the `⋮` button |
| Menu implementation | Native `<details>`/`<summary>` dropdown — no new JS |
| Rename UX | Inline text input (pre-filled) with Save/Cancel, swapped into the tree |
| Duplicate scope | Deep copy: project + all contributions, results, skill evidence, stories (new IDs) |
| Duplicate name | `"<original name> (copy)"` |
| Archive behavior | Set `Project.status = "archived"`; filter archived rows out of the tree |
| Archive confirm | `hx-confirm` prompt before archiving |
| Restore/unarchive UI | Out of scope for now (data kept in DB, recoverable later) |
| Schema change | None — reuse existing `Project.status` field |
| Dependencies | No new libraries |

## Behavior

### 1. Expanded by default
- In `partials/tree.html`, render each experience `<details>` with `open` unconditionally. Users can still collapse manually.

### 2. Three-dots menu
- Rendered only when `selected_project_id == project.id`.
- A native `<details class="proj-menu">` with a `⋮` `<summary>` toggle and a dropdown list containing Rename / Duplicate / Archive.
- Positioned to the right of the project name (flex row).

### 3. Actions (all HTMX, target `#tree-panel`, re-render tree)
- **Rename** → `GET /partials/projects/{id}/rename-form` swaps the project row for an inline form; `POST /projects/{id}/rename` calls `update_project` with the new `project_name`, then re-renders the tree. Blank name → validation error, form re-shown.
- **Duplicate** → `POST /projects/{id}/duplicate` performs a deep copy via a new repo helper `duplicate_project(project_id)`, then re-renders the tree with the copy present.
- **Archive** → `POST /projects/{id}/archive` sets `status = "archived"` via `update_project` (with `hx-confirm`), then re-renders the tree without the archived project.

## Backend

- **Repository**
  - Add `duplicate_project(self, project_id: str) -> Project | None`: loads the project and its leaf entities, creates a new `Project` (new id, name `"<name> (copy)"`, `status` reset to non-archived), and copies each contribution/result/skill evidence/story with new ids pointing at the new project id. Returns the new project.
- **Tree data filtering**
  - In `_tree_data`, exclude projects with `status == "archived"` in both the non-search and search paths, so archived projects never appear in the tree.
- **Routes** (in `career_agent/ui/app.py`)
  - `GET /partials/projects/{project_id}/rename-form` — returns inline rename form partial.
  - `POST /projects/{project_id}/rename` — updates name, re-renders tree (HTMX) or redirects.
  - `POST /projects/{project_id}/duplicate` — deep copy, re-renders tree.
  - `POST /projects/{project_id}/archive` — sets archived status, re-renders tree.
  - All reuse the existing `_render_tree` / tree partial rendering path and preserve `selected_project_id` and current search `q` where applicable.

## Templates & Styles

- `partials/tree.html`: `open` on `<details>`; add the `⋮` menu markup for the selected project; add inline rename form branch.
- New partial: `partials/rename_project_form.html` for the inline rename input (Save/Cancel), swapped into `#tree-panel`.
- `workspace.html` `<style>`: add `.proj-menu` dropdown styles (toggle button, popover list, menu items) using existing tokens (`--border`, `--accent-soft`, `--radius`). Hide the default `<summary>` marker.

## Error Handling

- Rename with blank/whitespace name → 400-style inline error, form re-shown with entered value.
- Rename/Duplicate/Archive on missing project id → 404 (matches existing project routes).
- Archive is guarded by `hx-confirm`; no separate server confirmation.

## Testing

- Repo: `duplicate_project` deep-copies project + all four leaf types with new ids and correct parent links; original unchanged.
- Tree data: archived projects excluded from `_tree_data` (search and non-search).
- Routes: rename updates name; duplicate adds a copy; archive removes project from rendered tree.
- Template: selected project shows `⋮` menu; non-selected does not; `<details>` renders `open`.

## Out of Scope

- Restoring/unarchiving via the UI.
- Bulk actions, drag-reordering, or archiving experiences.
- Persisting expand/collapse state across reloads.
