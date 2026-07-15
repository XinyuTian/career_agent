# Career Workspace UI Redesign (Phase 1)

Date: 2026-07-14  
Status: Approved for planning (pending final user review of this doc)

## Goal

Replace the multi-page monospace UI with a three-panel **career workspace**: left navigator, center project tabs with panel-level Edit/Save, and a right Paste-notes assistant that runs scoped Agent 1 import. Phase 1 uses only the existing SQLite data model (no new tables/columns for Overview). Phase 2 (out of this doc’s implementation scope beyond a stub note) adds completeness scoring and conversational interviewer in the right panel.

## Decisions

| Topic | Choice |
|-------|--------|
| Scope phasing | **B** — Phase 1: shell + tabs + Edit/Save; Phase 2: completeness + interviewer |
| Stack | FastAPI + Jinja + **HTMX** (keep Python backend) |
| Overview data | Existing `Project` fields only — no new narrative columns |
| Experience click | Expands/collapses tree only; center stays “Select a project” |
| Editing UX | Panel-level **Edit** / **Save** / **Cancel** (not per-section inline Edit) |
| Plain-text AI fill | Enabled; Phase 1 lives in the **right panel** |
| Add experience | Control directly under the sidebar search bar |
| Add project | Control on the right of each Experience (org) row |

## Architecture

```
┌─────────────┬──────────────────────────────┬─────────────────┐
│  Left       │  Center                      │  Right          │
│  Navigator  │  Project workspace (tabs)    │  Paste notes    │
│  HTMX tree  │  Read ↔ Edit mode (HTMX)     │  Agent 1 import │
└─────────────┴──────────────────────────────┴─────────────────┘
         │                    │                        │
         └────────────── CareerRepository / agents ────┘
```

Server-rendered shell with HTMX partials for:

- Tree expand / project selection (center swap)
- Tab switches within a project
- Enter/exit Edit mode and Save/Cancel for the active tab
- Notes import result refresh

## Layout

### Left — Career navigator

- Search input: client-side filter over Experience organization/title and Project names
- **+ Add experience** immediately below search
- Collapsible tree:
  - Experience row: display name (e.g. organization or “org — title”); **+ Add project** on the right of that row
  - Nested projects under each experience
- Selecting an Experience: expand/collapse only
- Selecting a Project: load center workspace for that `project_id`
- Add experience / add project: small modal or inline panel forms posting to repository create endpoints, then refresh tree

### Center — Project workspace

Shown only when a project is selected; otherwise placeholder: “Select a project”.

**Header:** project name + parent experience label.

**Tabs:** Overview | Contributions | Results | Skills | Stories

**Mode control (per tab):**  
Read mode by default. Top-right of the tab content: **Edit**. In edit mode: **Save** and **Cancel**.

#### Overview (existing Project fields only)

| UI label | Field |
|----------|--------|
| Problem | `problem` |
| Business context | `business_context` |
| Your role | `personal_role` |
| Stakeholders | `users_or_stakeholders` |
| Responsibilities | `responsibilities` |
| Stage | `project_stage` |
| Timeline | `timeline` |
| Status | `status` |

Empty fields show a light “Not set yet” placeholder in read mode.

Save Overview → single `update_project` (or equivalent) for all edited fields.

Optional footer (read-only counts): “N contributions · N results · N skills · N stories” linking to tabs — no new data.

#### Leaf tabs (Contributions / Results / Skills / Stories)

- **Read:** list of cards for entities of that type under the project
- **Edit:** same list as editable forms; allow add row / remove row (remove = delete on Save, or explicit delete with confirm in edit mode)
- **Save:** batch create/update/delete via repository for that entity type only

Field sets match existing models (`Contribution`, `Result`, `SkillEvidence`, `Story`). Skills tab = `skill_evidence` table.

### Right — Paste notes (Phase 1)

- Title: “Paste notes”
- Enabled when a project is selected; otherwise prompt to select a project
- Textarea + Submit → existing `CareerKnowledgeBuilderAgent.extract_from_notes(..., project_id=...)`
- After submit: show created/updated/conflict summary and any new open questions for the project
- This is the primary free-text → structured DB path; Edit/Save remains for precise corrections

## Phase 2 (documented, not built in Phase 1)

Right panel upgrades to:

- Project completeness % and missing-item list
- Per item: **Answer now** / **Mark as unknown**
- Conversational interviewer

Paste notes may become a sub-section or tab within that assistant. Completeness rules and interview UX will get their own spec before implementation.

## Routes (sketch)

Keep FastAPI; reshape around workspace:

- `GET /` — shell (tree + empty center + right stub state)
- `GET /partials/tree` — navigator fragment (search query optional)
- `GET /partials/projects/{id}?tab=overview` — center tab (read)
- `GET /partials/projects/{id}/edit?tab=...` — center tab (edit form)
- `POST /partials/projects/{id}?tab=overview` — save overview
- `POST /partials/projects/{id}/leaves?type=contribution` — save leaf tab batch
- `POST /experiences`, `POST /experiences/{id}/projects` — create from sidebar
- `POST /projects/{id}/notes` — paste-notes import (existing behavior)

Exact paths may be adjusted in the implementation plan; behavior above is normative.

## Error handling

- Unknown project/experience id → 404 fragment or flash
- Blank required names on create (organization, title, project_name) → 400, re-show form with error (same rule as current UI)
- Agent/import failures → message in right panel without wiping center state
- Save with validation errors → stay in edit mode and show field errors

## Testing

- Tree: create experience/project; project selection loads overview
- Overview read/edit/save/cancel for project fields
- Each leaf tab save create + update
- Notes import scoped to project; result message appears
- No project selected: center + right disabled messaging

## Non-goals (Phase 1)

- Completeness scoring / Mark as unknown
- Interviewer chat
- New DB columns for Overview narrative synonyms
- Separate SPA or React frontend
- Resume tailor UI

## Success criteria

1. Three-panel shell works with search, add experience under search, add project beside org rows.
2. Selecting a project shows tabs; experience click does not replace the center with an experience editor.
3. Overview uses only existing Project fields; Edit/Save/Cancel at panel level.
4. Leaf tabs support read + panel Edit/Save against existing leaf models.
5. Right panel paste-notes runs scoped Agent 1 import.
6. Existing CLI agents/repos remain the write path; UI is another front door.
