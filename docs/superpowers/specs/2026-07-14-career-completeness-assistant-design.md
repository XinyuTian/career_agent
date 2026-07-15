# Career Completeness Assistant (Phase 2)

Date: 2026-07-14  
Status: Approved for planning (pending final user review of this doc)  
Depends on: Phase 1 workspace UI (`2026-07-14-career-workspace-ui-design.md`)

## Goal

Upgrade the workspace right panel into a **completeness assistant**: show project completeness %, list missing items from structural rules plus open questions, let the user answer or mark unknown via hover-revealed actions, and keep Paste notes stacked below. Conversational interviewer chat is deferred.

## Decisions

| Topic | Choice |
|-------|--------|
| Phase 2 scope | Completeness + Answer/Unknown first; interviewer later |
| Gap sources | Hybrid: deterministic structural rules + open `OpenQuestion` rows |
| Action reveal | Hover shows **Answer now** / **Mark as unknown**; click Answer now opens form |
| Answer UX | Inline answer form in the right panel (not navigate to center Edit) |
| Mark as unknown | OpenQuestion → `status=dismissed`; structural → `dismissed_gaps` row |
| Right panel layout | Completeness block stacked above Paste notes |
| Scoring | Dismissed/unknown gaps excluded from denominator |

## Right-panel layout

When a project is selected:

```
Project completeness: NN%

Missing:
- <gap label>          ← hover → [Answer now] [Mark as unknown]
  (expanded Answer now form appears under the row when chosen)

────────────────────────
Paste notes
[existing import form]
```

When no project is selected: keep current messaging (select a project; paste notes disabled).

Hover: CSS `:hover` (and keyboard `:focus-within` for accessibility) reveals the two action buttons. Buttons are not always visible.

## Completeness engine

Module: `career_agent/completeness.py` (pure functions over repository data).

### Structural rules (v1)

For the selected project:

| Gap key | Condition | Label (example) |
|---------|-----------|-----------------|
| `overview.problem` | `problem` empty | Problem not set |
| `overview.business_context` | `business_context` empty | Business context not set |
| `overview.personal_role` | `personal_role` empty | Your role not set |
| `overview.users_or_stakeholders` | `users_or_stakeholders` empty | Stakeholders not set |
| `coverage.contributions` | zero contributions | No contributions recorded |
| `coverage.results` | zero results | No results recorded |
| `coverage.skills` | zero skill evidence | No skill evidence recorded |
| `coverage.stories` | zero stories | No stories recorded |
| `contribution.{id}.ownership_level` | contribution exists, `ownership_level` empty | Ownership unclear on: {action} |
| `result.{id}.baseline` | `metric_name` set and `baseline` empty | No baseline for: {metric_name} |
| `skill.{id}.evidence` | skill evidence exists, `evidence` empty | Skill evidence thin for: {skill} |

Rules may be extended later without changing the UI contract.

### Open-question gaps

Include each `OpenQuestion` with `status=open` whose `related_entity_id` is:

- the project id, or
- any leaf id belonging to that project

Label = `question` text (optionally with `why_it_matters` as secondary muted line).

Gap key = `open_question.{id}`.

### Score

1. Build the full **checklist** of checks that apply to this project:
   - always: four overview field checks + four coverage checks
   - plus per-existing-leaf depth checks (ownership / baseline / evidence)
   - plus each open `OpenQuestion` for the project/leaves (as failing checks)
2. Remove checklist items whose structural `gap_key` is in `dismissed_gaps`, or whose OpenQuestion status is not `open`.
3. **Missing** = checklist items that currently fail.
4. **Percent** = `round(100 * (len(checklist) - len(missing)) / max(len(checklist), 1))`.

Dismissed gaps do not appear in Missing and do not reduce the score.

## Persistence

### `dismissed_gaps` (new table)

| Column | Type |
|--------|------|
| project_id | TEXT NOT NULL |
| gap_key | TEXT NOT NULL |
| created_at | TEXT NOT NULL |
| PRIMARY KEY (project_id, gap_key) |

No UI to clear dismissed gaps in this slice (YAGNI).

### OpenQuestion status values

- `open` — counts as missing  
- `resolved` — answered successfully  
- `dismissed` — Mark as unknown  

Existing Agent 1 import continues to create `open` questions.

## Actions

### Mark as unknown

- Structural gap → `INSERT OR IGNORE` into `dismissed_gaps`  
- OpenQuestion gap → `update` status to `dismissed`  
- Refresh right panel (recompute %)

### Answer now

1. Hover reveals buttons; click **Answer now** expands a textarea + Submit/Cancel under that row.  
2. On submit:

| Gap kind | Write path |
|----------|------------|
| Overview field (`overview.*`) | Patch that Project field with answer text; if non-empty, gap clears |
| Leaf field (`contribution.*.ownership_level`, etc.) | Patch that leaf field |
| Coverage (`coverage.*`) | Scoped Agent 1 `extract_from_notes` with the answer as notes (same as Paste notes); gap clears if imports create the missing category |
| OpenQuestion | Scoped Agent 1 import of `Question: {q}\nAnswer: {a}`; set that OpenQuestion to `resolved` on success |

3. After success: refresh right panel; OOB refresh center (overview or relevant leaf tab) when fields/leaves changed.

Failures surface a message in the right panel without clearing center state.

## Routes (additive)

- Extend right-panel partial to include completeness block + paste notes  
- `POST /projects/{id}/gaps/{gap_key}/unknown` — mark unknown  
- `POST /projects/{id}/gaps/{gap_key}/answer` — submit answer form  
- Right panel reload on project select already exists; completeness computed server-side each render  

## Testing

- Structural gaps appear for empty overview fields  
- Open questions for project/leaves appear in Missing  
- Hover/focus-within reveals actions (template structure test; full hover optional)  
- Mark unknown dismisses structural key and OQ  
- Answer now patches overview field and lifts that gap  
- Score excludes dismissed items  
- Paste notes still works below the completeness block  

## Non-goals

- Conversational interviewer  
- Experience-level completeness  
- Editing completeness rule weights in UI  
- Clearing dismissed gaps  
- Changing center Edit/Save  

## Success criteria

1. Selecting a project shows completeness % and a Missing list from rules + open questions.  
2. Hover reveals Answer now / Mark as unknown; Answer now expands inline.  
3. Mark as unknown persists and removes the item from Missing / score penalty.  
4. Answer now writes through repository / Agent 1 paths above and refreshes the panel.  
5. Paste notes remains stacked under the assistant.  
6. No interviewer chat in this slice.
