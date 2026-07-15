# Career Workspace Visual Restyle

Date: 2026-07-14  
Status: Approved for planning (pending final user review of this doc)  
Depends on: Phase 1 workspace UI, Phase 2 completeness assistant  
Reference mockup: user-provided three-panel workspace design

## Goal

Restyle the existing HTMX career workspace to match the approved visual mockup (fonts, colors, spacing, controls, and light layout hierarchy) **without** changing product behavior: panel-level Edit/Save/Cancel, hover gap actions, Paste notes (no interviewer CTA), and the current Overview field set.

## Decisions

| Topic | Choice |
|-------|--------|
| Scope | Visual polish + light layout alignment |
| CSS delivery | Design tokens + styles in `workspace.html` (no separate CSS file, no Tailwind) |
| Right-panel CTA | No **Continue interview**; keep Completeness + Paste notes |
| Edit UX | Keep panel-level Edit/Save/Cancel (no per-section Edit links) |
| Gap actions | Keep Phase 2 hover/focus reveal for Answer now / Mark as unknown |
| Data/schema | No new fields; mockup “Methods” tags are illustrative only |

## Design system

Tokens in `:root` inside `workspace.html`:

| Token | Role | Approx. value |
|-------|------|----------------|
| `--bg-page` | Page background | `#F3F4F6` |
| `--bg-panel` | Panel surface | `#FFFFFF` |
| `--border` | Panel/input borders | `#E5E7EB` |
| `--text` | Headings | `#111827` |
| `--text-muted` | Body / secondary | `#6B7280` |
| `--accent` | Primary buttons, links, bar fill | `#3B82F6` |
| `--accent-soft` | Active tab, selected row, tags, badge | `#EFF6FF` |
| `--accent-text` | Badge / soft-surface text | `#1D4ED8` |
| `--radius` | Inputs, buttons, panels | `10px` |

- **Typography:** Inter (Google Fonts) with system-ui fallback; replace monospace.
- **Primary button:** solid `--accent`, white text.
- **Secondary button:** white background, `--border` outline (e.g. `+ Add`).
- **Panels:** white surfaces on gray page, light border, rounded corners, ~24px padding.

## Layout

Keep grid `280px | 1fr | 320px`.

### Left — Experiences

- Header: **Experiences** + secondary **+ Add** (existing add-experience HTMX flow)
- Search placeholder: **Search**
- Tree hierarchy: organization (parent) → muted role/title line → nested projects
- Selected project: `--accent-soft` background pill
- **+ Add project** remains on the experience row; secondary styling

### Center — Project workspace

- Title + soft status badge when `project.status` is set
- Subtitle: `Organization · Title`
- Tabs as soft pills; active tab uses `--accent-soft`
- Panel-level Edit (read) / Save + Cancel (edit) as primary/secondary buttons
- Overview: spaced sections with bold labels and muted body text; same fields as today (Problem, Business context, Your role, Stakeholders, Responsibilities, Stage, Timeline, Status)
- Leaf tabs keep list/card semantics; restyle only

### Right — Completeness + Paste notes

- Completeness label + percent + horizontal progress bar
- Gap list heading: **Needs clarification** (label rename only)
- Gap rows: existing Answer now / Mark as unknown on hover/focus
- Paste notes block unchanged functionally; restyled inputs/buttons
- No interviewer / Continue interview control

## Implementation notes

- Prefer CSS class additions and small Jinja structure tweaks over route/repository changes.
- Selected project highlight: pass optional `selected_project_id` into tree partial renders (e.g. query param on `/partials/tree`, and refresh or OOB-update the tree when a project is selected) so the soft-blue pill persists across search/re-renders. No repository changes.
- No schema/completeness-rule changes.

## Out of scope

- Conversational interviewer / Continue interview CTA
- Per-section or inline Edit
- Always-visible gap action buttons
- Methods tags or other new Overview fields
- Extracting `static/workspace.css` or adopting Tailwind
- Intentional HTMX flow redesigns

## Verification

- Visual check of three panels vs mockup (type, color, selection, tabs, progress)
- Smoke: search, select project, switch tabs, Edit/Save/Cancel, paste notes, gap answer/unknown
- Run existing pytest suite (expect no logic regressions)
