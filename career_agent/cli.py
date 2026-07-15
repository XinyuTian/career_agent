from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .agents import (
    CareerKnowledgeBuilderAgent,
    ResumeTailoringAgent,
    embed_missing_leaves,
)
from .ai_builder import AIBuilderClient
from .config import load_settings
from .repository import CareerRepository


def build_client() -> AIBuilderClient:
    return AIBuilderClient(load_settings())


def build_repository() -> CareerRepository:
    # Resolve the path at command execution time so callers can override config.DB_PATH.
    return CareerRepository(config.DB_PATH)


def read_text_arg(value: str) -> str:
    path = Path(value)
    try:
        is_file = path.exists() and path.is_file()
    except OSError:
        is_file = False
    if is_file:
        return path.read_text(encoding="utf-8")
    return value


def cmd_import_notes(args: argparse.Namespace) -> int:
    client = build_client()
    repo = build_repository()
    agent = CareerKnowledgeBuilderAgent(client, repo)
    result = agent.extract_from_notes(
        read_text_arg(args.notes),
        project_id=args.project_id,
        experience_id=args.experience_id,
    )
    created = sum(result.get("created", {}).values())
    updated = sum(result.get("updated", {}).values())
    conflicts = len(result.get("conflicts", []))
    print(f"Created: {created}")
    print(f"Updated: {updated}")
    print(f"Conflicts: {conflicts}")
    return 0


def cmd_questions(args: argparse.Namespace) -> int:
    client = build_client()
    repo = build_repository()
    agent = CareerKnowledgeBuilderAgent(client, repo)
    for question in agent.generate_interview_questions(args.focus):
        print(f"- {question}")
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    client = build_client()
    repo = build_repository()
    count = embed_missing_leaves(client, repo)
    print(f"Embedded {count} leaves.")
    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    client = build_client()
    repo = build_repository()
    missing = len(repo.list_unembedded_leaves())
    if missing:
        print(f"Embedding {missing} leaves before retrieval...")
        embed_missing_leaves(client, repo)
    agent = ResumeTailoringAgent(client, repo)
    target = agent.tailor_resume(read_text_arg(args.jd), limit=args.limit)
    print(f"Saved tailored resume package to {target}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    counts = build_repository().counts()
    labels = (
        ("Experiences", "experiences"),
        ("Projects", "projects"),
        ("Contributions", "contributions"),
        ("Results", "results"),
        ("Skill evidence", "skill_evidence"),
        ("Stories", "stories"),
        ("Open questions", "open_questions"),
        ("Embedded leaves", "embeddings"),
    )
    for label, key in labels:
        print(f"{label}: {counts[key]}")
    return 0


def cmd_list_experiences(args: argparse.Namespace) -> int:
    for experience in build_repository().list_experiences():
        print(
            f"{experience.id}\t{experience.organization}\t{experience.title}"
            f"\t{experience.start_date or ''}\t{experience.end_date or ''}"
        )
    return 0


def cmd_list_projects(args: argparse.Namespace) -> int:
    for project in build_repository().list_projects(args.experience_id):
        print(f"{project.id}\t{project.experience_id}\t{project.project_name}")
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    try:
        from .ui.app import run
    except ImportError as exc:
        raise RuntimeError(
            "The local UI is not available yet; install the UI dependencies "
            "after the UI module is added."
        ) from exc
    run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-first career knowledge base and resume tailoring agents.")
    sub = parser.add_subparsers(required=True)

    import_notes = sub.add_parser("import-notes", help="Extract structured career evidence from notes or a text file.")
    import_notes.add_argument("notes", help="Raw notes text or path to a text file.")
    import_notes.add_argument("--project-id", help="Merge notes into an existing project.")
    import_notes.add_argument("--experience-id", help="Merge notes into an existing experience.")
    import_notes.set_defaults(func=cmd_import_notes)

    questions = sub.add_parser("questions", help="Generate interview questions for Agent 1.")
    questions.add_argument("--focus", help="Optional focus area, such as a role, project, or skill.")
    questions.set_defaults(func=cmd_questions)

    embed = sub.add_parser("embed", help="Embed all leaf rows that do not yet have vectors.")
    embed.set_defaults(func=cmd_embed)

    tailor = sub.add_parser("tailor", help="Generate a tailored resume package from a JD text file or pasted JD.")
    tailor.add_argument("jd", help="Job description text or path to a text file.")
    tailor.add_argument("--limit", type=int, default=10, help="Number of evidence records to retrieve.")
    tailor.set_defaults(func=cmd_tailor)

    status = sub.add_parser("status", help="Show local career database status.")
    status.set_defaults(func=cmd_status)

    experiences = sub.add_parser("list-experiences", help="List career experiences.")
    experiences.set_defaults(func=cmd_list_experiences)

    projects = sub.add_parser("list-projects", help="List career projects.")
    projects.add_argument("--experience-id", help="Only list projects for this experience.")
    projects.set_defaults(func=cmd_list_projects)

    ui = sub.add_parser("ui", help="Start the local career database UI.")
    ui.set_defaults(func=cmd_ui)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
