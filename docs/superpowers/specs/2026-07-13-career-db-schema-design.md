# Career Knowledge Database Schema & Agent Sync

Date: 2026-07-13  
Status: Approved for planning (pending final user review of this doc)

## Goal

Replace the flat JSON `EvidenceRecord` knowledge base with a relational SQLite career database that mirrors a hierarchical evidence model (Experience → Project → leaf evidence). Sync Agent 1 (Career Knowledge Builder) to fill and merge into this database, keep Agent 2 retrieving from leaf embeddings, and ship a minimal local UI for browsing and project-scoped note intake.

## Decisions

| Topic | Choice |
|-------|--------|
| Storage | SQLite at `data/career.db` (stdlib `sqlite3`) |
| Import strategy | Hybrid: extract what notes prove; emit OpenQuestions for gaps |
| Entity matching | Exact unique keys first; LLM-assisted IDs next; OpenQuestion on ambiguity |
| Merge | Append/fill missing; on scalar conflict keep existing + OpenQuestion |
| Embeddings | Leaf-centric: Contribution, Result, SkillEvidence, Story |
| Profile | Keep `data/profile.json` unchanged for now |
| Scope | Backend (schema + Agent 1/2 + CLI) **and** minimal browse/import UI |
| UI stack | FastAPI + Jinja + uvicorn; `career-agent ui` on localhost |
| Migration | None — flat JSON KB not populated; retire the path |
| LLM/embeddings API | AI Builder Space Backend per [OpenAPI](https://space.ai-builders.com/backend/openapi.json) |

## External API (AI Builder Space)

Source of truth: `https://space.ai-builders.com/backend/openapi.json`  
Base URL: `https://space.ai-builders.com/backend` (configurable via env)

### Auth

- HTTP Bearer (`bearerAuth` in OpenAPI): `Authorization: Bearer <token>`
- Env: prefer `AI_BUILDER_TOKEN` (platform convention). Also accept `AI_BUILDER_API_KEY` as an alias so existing `.env` files keep working.
- Never hardcode tokens; `.env` stays gitignored.

### Endpoints used by this project

| Purpose | Method / path | Request (OpenAPI) |
|---------|---------------|-------------------|
| Agent JSON/text generation | `POST /v1/chat/completions` | `ChatCompletionRequest` (`model`, `messages`, `temperature`, `max_tokens`, …) |
| Leaf embeddings | `POST /v1/embeddings` | `EmbeddingRequest` (`input`, `model`, optional `dimensions`) |
| Optional diagnostics | `GET /v1/models` | list available models |

Client behavior:

- Keep a thin `AIBuilderClient` aligned to these schemas (stdlib `urllib` is fine; no need for a generated SDK unless it reduces bugs).
- Defaults: chat model from env (e.g. `deepseek` or OpenAPI default `supermind-agent-v1`); embedding model `text-embedding-3-small`.
- Respect model quirks documented in OpenAPI (e.g. some models force `temperature=1.0`; `gpt-5` maps `max_tokens` → `max_completion_tokens` server-side).
- Structured Agent 1/2 output continues via prompt schema + JSON parse (OpenAPI has no separate JSON-schema response mode on chat).

### Env example

```bash
AI_BUILDER_TOKEN=your_token_here
# or: AI_BUILDER_API_KEY=your_key_here
AI_BUILDER_BASE_URL=https://space.ai-builders.com/backend
AI_BUILDER_CHAT_MODEL=deepseek
AI_BUILDER_EMBEDDING_MODEL=text-embedding-3-small
```

## Architecture

```
CLI / Minimal UI
        │
        ▼
 CareerKnowledgeBuilderAgent / ResumeTailoringAgent
        │
        ▼
 Repository layer (Python)  ──►  SQLite data/career.db
        │
        ▼
 Embeddings table (leaf entities only)  ──►  Agent 2 retrieval
```

Shared repositories are the single write path. CLI and UI call the same agent + repo functions. No dual JSON/SQLite writes.

## Data model

### Conventions

- Primary keys: UUID strings.
- Timestamps: `created_at`, `updated_at` (ISO-8601 UTC) on every table.
- List-valued / nested fields (e.g. responsibilities, collaborators): JSON text columns.
- Cascades: deleting an Experience deletes its Projects; deleting a Project deletes its leaf rows and related open questions that point at those entities.

### Experience

Professional frame: company, research position, personal project, volunteer role, or other.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| organization | TEXT | |
| title | TEXT | |
| employment_type | TEXT | nullable |
| start_date | TEXT | nullable (ISO date or year-month) |
| end_date | TEXT | nullable |
| team | TEXT | nullable |
| manager_level | TEXT | nullable |
| business_context | TEXT | nullable |
| reason_for_joining | TEXT | nullable |
| reason_for_leaving | TEXT | nullable |
| created_at / updated_at | TEXT | |

Unique match key: `(organization, title, start_date)`.  
Note: if `start_date` is null, uniqueness is weak in SQLite (multiple nulls allowed); fall back to LLM id / OpenQuestion when org+title collide without dates.

### Project

Belongs to one Experience; each experience can have many projects.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| experience_id | TEXT FK → experiences | CASCADE |
| project_name | TEXT | |
| problem | TEXT | nullable |
| business_context | TEXT | nullable |
| users_or_stakeholders | TEXT | nullable freeform text |
| personal_role | TEXT | nullable |
| responsibilities | TEXT | JSON array |
| project_stage | TEXT | nullable |
| timeline | TEXT | nullable |
| status | TEXT | nullable |
| created_at / updated_at | TEXT | |

Unique match key: `(experience_id, project_name)`.

### Contribution

Atomic “what I did” under a project.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| project_id | TEXT FK → projects | CASCADE |
| action | TEXT | |
| technical_method | TEXT | nullable |
| decision_made | TEXT | nullable |
| difficulty | TEXT | nullable |
| alternative_considered | TEXT | nullable |
| collaborators | TEXT | JSON array |
| ownership_level | TEXT | nullable |
| created_at / updated_at | TEXT | |

No forced unique key. Merge preference: exact `action` match within project when present; else LLM id or insert.

### Result

Measured or qualitative outcomes for a project.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| project_id | TEXT FK → projects | CASCADE |
| result_type | TEXT | nullable |
| metric_name | TEXT | nullable |
| baseline | TEXT | nullable |
| final_value | TEXT | nullable |
| absolute_change | TEXT | nullable |
| relative_change | TEXT | nullable |
| business_impact | TEXT | nullable |
| confidence_level | TEXT | nullable |
| measurement_method | TEXT | nullable |
| is_estimate | INTEGER | 0/1; default 0 |
| created_at / updated_at | TEXT | |

Soft match: `(project_id, metric_name)` when `metric_name` non-null; else LLM id or insert.

### SkillEvidence

Evidence of skill *use*, not a bare skill tag.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| project_id | TEXT FK → projects | CASCADE |
| skill | TEXT | |
| proficiency | TEXT | nullable |
| evidence | TEXT | nullable |
| recency | TEXT | nullable |
| frequency | TEXT | nullable |
| independently_used | INTEGER | 0/1 nullable |
| created_at / updated_at | TEXT | |

Unique match key: `(project_id, skill)`.

### Story

Behavioral-interview STAR (+ reflection) stories.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| project_id | TEXT FK → projects | CASCADE |
| competency | TEXT | nullable |
| situation | TEXT | nullable |
| task | TEXT | nullable |
| action | TEXT | nullable |
| result | TEXT | nullable |
| conflict | TEXT | nullable |
| lesson | TEXT | nullable |
| what_you_would_change | TEXT | nullable |
| created_at / updated_at | TEXT | |

Soft match: `(project_id, competency)` when competency non-null; else LLM id or insert.

### OpenQuestion

Tracks gaps and merge conflicts for later interview/UI work.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | |
| related_entity_type | TEXT | experience \| project \| contribution \| result \| skill_evidence \| story |
| related_entity_id | TEXT | |
| question | TEXT | |
| why_it_matters | TEXT | nullable |
| priority | TEXT | e.g. high \| medium \| low |
| status | TEXT | open \| resolved \| dismissed |
| created_at / updated_at | TEXT | |

No uniqueness constraint. Agent may create duplicates intentionally; UI may later de-dupe.

### Embeddings

| Column | Type | Notes |
|--------|------|-------|
| entity_type | TEXT | contribution \| result \| skill_evidence \| story |
| entity_id | TEXT | |
| embedding | TEXT | JSON array of floats |
| updated_at | TEXT | |

PK: `(entity_type, entity_id)`.

Searchable text for a leaf = leaf fields + parent project name + parent experience org/title (for context), without inventing content.

## Agent 1: Knowledge Builder sync

### Prompt / output schema

Replace flat `KNOWLEDGE_BUILDER_SCHEMA` with hierarchical JSON matching the tables above, plus:

- Optional `id` on each entity (existing UUID or null for create)
- `open_questions[]`
- Optional `profile` merge (same as today into `profile.json`)

System instruction preserves current principles: no resume bullets, no job-specific optimization, null for unknown, no invention.

### Import flow (`import-notes`)

1. Load compact existing graph summary (experience/project ids + match keys; optionally leaf titles).
2. If `--project-id` or `--experience-id` set, constrain extraction and matching to that scope (UI always scopes to project).
3. Call model with notes + summary + scope.
4. Apply persistence merge (repository layer, not the model):

   **Match order**
   1. Exact unique / soft keys
   2. Explicit existing `id` from model if it still resolves and is in scope
   3. Else create new row
   4. If model `id` conflicts with exact-key identity → do not overwrite; insert OpenQuestion describing ambiguity

   **Field merge**
   - Empty/null loses to non-empty
   - List fields: union of unique values
   - Scalar conflict (both non-empty, differ): keep existing value; create OpenQuestion for the conflict
   - On leaf text change: delete that leaf’s embedding row so `embed` reprocesses it

5. Return counts (created/updated) and open questions for CLI/UI display.

### Questions flow

`career-agent questions` (and UI later):

1. Load unresolved OpenQuestions ordered by priority.
2. Optionally generate additional interview questions from profile + focus + thin graph summary.
3. Present both (DB gaps first).

## Agent 2: Resume tailoring

1. Analyze JD (unchanged intent).
2. Embed JD query; cosine-search leaf embeddings.
3. For each match, load leaf + parent Project + Experience as evidence context.
4. Generate resume + truth check from evidence only (same guardrails).
5. Save package under `generated_resumes/` as today.

Auto-embed unembedded leaves before retrieve (same behavior as today’s unembedded records).

## CLI surface

| Command | Behavior |
|---------|----------|
| `import-notes <text\|file> [--project-id] [--experience-id]` | Hierarchical extract + merge |
| `questions [--focus]` | OpenQuestions + generated prompts |
| `embed` | Embed leaf rows missing vectors |
| `tailor <jd> [--limit]` | Leaf retrieval + resume package |
| `status` | Counts: experiences, projects, leaves, open questions, embeddings |
| `list-experiences` | Inspect |
| `list-projects [--experience-id]` | Inspect |
| `ui` | Start local FastAPI app |

Retire reliance on `data/career_knowledge_base.json`.

## Minimal UI (v1)

### Stack

- FastAPI + Jinja2 templates + uvicorn
- Localhost only; command: `career-agent ui` (default `127.0.0.1:8765`)
- Same repository + agent modules as CLI

### Pages

1. **Experiences home** — list; form to create Experience.
2. **Experience detail** — show fields; list Projects; form to create Project.
3. **Project detail** — show project fields; read-only sections for contributions, results, skill evidence, stories, open questions; **Add notes** textarea → scoped Agent 1 import; flash created/updated + new open questions.
4. **Open questions** (thin) — unresolved list with links to related entity pages.

### Out of v1

- Live interview chat
- Inline edit of every field
- Conflict-resolution UI beyond OpenQuestion creation
- Resume tailor in browser
- Auth / remote deploy

## Error handling

- Missing API key / AI Builder failures: surface clear CLI/UI errors; do not partial-commit mid-entity graph if transaction available (wrap import apply in a SQLite transaction).
- Unknown `--project-id` / `--experience-id`: fail fast.
- Embedding dimension / empty DB: `tailor` warns when no leaf embeddings exist.

## Testing (minimal for first plan)

- Unit tests for merge rules (fill, append, scalar conflict → OpenQuestion).
- Unit tests for exact-key matching of Experience / Project / SkillEvidence.
- Schema smoke: create all table types and retrieve with parent context.
- Optional: mock AI client for import/tailor integration.

## Non-goals (this cycle)

- Migrating fictional/legacy flat JSON records
- Multi-user sync or cloud backup
- Rich design system for the UI (functional local tool aesthetic is enough)

## Success criteria

1. SQLite schema matches the seven entity types + embeddings.
2. `import-notes` (scoped and unscoped) merges without silent overwrites on conflicts.
3. `embed` + `tailor` work against leaf embeddings with parent context.
4. Minimal UI can create Experience/Project and import notes into a project window.
5. OpenQuestions appear from gaps and conflicts and feed `questions`.
