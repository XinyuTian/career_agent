# career_agent

Local-first AI career agent system with two separate agents:

- **Agent 1: Career Knowledge Builder** interviews, extracts, organizes, and stores verified career evidence locally.
- **Agent 2: Resume Tailoring Agent** parses a job description, retrieves relevant local evidence, drafts a targeted resume, and runs a truthfulness/ATS critique.

The key principle is local memory ownership: the API provides intelligence, but your work history is stored in this repo under `data/`. The app only sends the specific context needed for extraction, embeddings, or generation.

## Setup

```bash
cp .env.example .env
# add your AI_BUILDER_TOKEN to .env
python3 -m pip install -e .
```

Expected `.env`:

```bash
AI_BUILDER_TOKEN=your_token_here
# AI_BUILDER_API_KEY=your_key_here  # legacy alias for AI_BUILDER_TOKEN
AI_BUILDER_BASE_URL=https://space.ai-builders.com/backend
AI_BUILDER_CHAT_MODEL=deepseek
AI_BUILDER_EMBEDDING_MODEL=text-embedding-3-small
```

## Commands

Import notes into the local career database:

```bash
career-agent import-notes notes.txt
career-agent import-notes notes.txt --project-id <uuid> --experience-id <uuid>
```

Ask Agent 1 for interview questions:

```bash
career-agent questions --focus "platform engineering projects"
```

Embed leaf records that are missing vectors:

```bash
career-agent embed
```

Tailor a resume to a job description:

```bash
career-agent tailor job_description.txt
career-agent tailor job_description.txt --limit 15
```

`--limit` controls how many evidence records are retrieved and defaults to 10.

Browse existing data, create experiences and projects, or import notes in the
local web UI:

```bash
career-agent ui
```

Then open http://127.0.0.1:8765.

List stored entities:

```bash
career-agent list-experiences
career-agent list-projects
career-agent list-projects --experience-id <uuid>
```

Check local status:

```bash
career-agent status
```

## Local Files

- `data/career.db`: SQLite career knowledge base (see schema below)
- `data/profile.json`: local profile facts
- `generated_resumes/`: generated resume packages, saved with the JD, analysis, retrieved evidence, resume markdown, and truth check

## Career Database Schema

Evidence lives in `data/career.db` as seven related entities plus embeddings:

| Table | Role |
|-------|------|
| `experiences` | Jobs / roles (organization, title, dates, context) |
| `projects` | Work within an experience (problem, role, timeline) |
| `contributions` | Actions taken on a project |
| `results` | Measurable outcomes and business impact |
| `skill_evidence` | Skills demonstrated on a project |
| `stories` | STAR-style narratives tied to a project |
| `open_questions` | Ambiguities and conflicts awaiting human review |
| `embeddings` | Vector embeddings for leaf rows (contributions, results, skill_evidence, stories) |

Hierarchy: **experience → project → leaf** (contributions, results, skill_evidence, stories). Agent 1 resolves imports by exact key match, then LLM-assisted ID match, then create; scalar conflicts keep the existing value and raise an open question.

## Evidence Model

Each leaf record can capture:

- situation, task, actions, result
- skills, tools, stakeholders
- business impact and technical depth
- metrics and artifacts
- recruiter, manager, and engineer perspectives

Agent 2 retrieves embedded leaves plus parent project/experience context. It composes only from verified evidence and omits unsupported claims instead of inventing experience.
