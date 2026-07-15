"""Minimal local FastAPI UI for browsing and building the career knowledge base.

Functional local-tool aesthetic: plain HTML, tables and forms, no styling
frameworks. Each request opens its own SQLite connection scoped to the
configured database path.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from ..agents import CareerKnowledgeBuilderAgent
from ..ai_builder import AIBuilderClient
from ..config import load_settings
from ..models import Experience, Project
from ..repository import CareerRepository

DB_PATH: Path = config.DB_PATH

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def build_agent(repo: CareerRepository) -> CareerKnowledgeBuilderAgent:
    return CareerKnowledgeBuilderAgent(AIBuilderClient(load_settings()), repo)


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


_LEAF_HIDDEN_FIELDS = {"id", "project_id", "created_at", "updated_at"}


def _leaf_fields(leaf: Any) -> list[tuple[str, Any]]:
    return [
        (name.replace("_", " "), value)
        for name, value in asdict(leaf).items()
        if name not in _LEAF_HIDDEN_FIELDS and value not in (None, "", [])
    ]


def _redirect(url: str, *, flash: str | None = None) -> RedirectResponse:
    if flash:
        url = f"{url}?flash={quote(flash)}"
    return RedirectResponse(url, status_code=303)


def create_app(db_path: Path | None = None) -> FastAPI:
    resolved_path = db_path if db_path is not None else DB_PATH
    app = FastAPI(title="Career Agent")
    app.state.db_path = resolved_path

    def get_repo() -> CareerRepository:
        return CareerRepository(app.state.db_path)

    @app.get("/")
    def home(request: Request):
        repo = get_repo()
        experiences = repo.list_experiences()
        return templates.TemplateResponse(
            request,
            "experiences.html",
            {"experiences": experiences},
        )

    @app.post("/experiences")
    def create_experience(
        request: Request,
        organization: str = Form(...),
        title: str = Form(...),
        employment_type: str = Form(""),
        start_date: str = Form(""),
        end_date: str = Form(""),
        team: str = Form(""),
        manager_level: str = Form(""),
        business_context: str = Form(""),
        reason_for_joining: str = Form(""),
        reason_for_leaving: str = Form(""),
    ):
        repo = get_repo()
        organization = organization.strip()
        title = title.strip()
        if not organization or not title:
            return templates.TemplateResponse(
                request,
                "experiences.html",
                {
                    "experiences": repo.list_experiences(),
                    "error": "Organization and title are required.",
                },
                status_code=400,
            )
        experience = Experience(
            id=_new_id(),
            organization=organization,
            title=title,
            employment_type=employment_type.strip() or None,
            start_date=start_date.strip() or None,
            end_date=end_date.strip() or None,
            team=team.strip() or None,
            manager_level=manager_level.strip() or None,
            business_context=business_context.strip() or None,
            reason_for_joining=reason_for_joining.strip() or None,
            reason_for_leaving=reason_for_leaving.strip() or None,
        )
        repo.create_experience(experience)
        return _redirect("/", flash=f"Added experience: {experience.organization} — {experience.title}")

    @app.get("/experiences/{experience_id}")
    def experience_detail(request: Request, experience_id: str):
        repo = get_repo()
        experience = repo.get_experience(experience_id)
        if experience is None:
            raise HTTPException(status_code=404, detail="Experience not found")
        projects = repo.list_projects(experience_id)
        return templates.TemplateResponse(
            request,
            "experience_detail.html",
            {"experience": experience, "projects": projects},
        )

    @app.post("/experiences/{experience_id}/projects")
    def create_project(
        request: Request,
        experience_id: str,
        project_name: str = Form(...),
        problem: str = Form(""),
        business_context: str = Form(""),
        users_or_stakeholders: str = Form(""),
        personal_role: str = Form(""),
        responsibilities: str = Form(""),
        project_stage: str = Form(""),
        timeline: str = Form(""),
        status: str = Form(""),
    ):
        repo = get_repo()
        experience = repo.get_experience(experience_id)
        if experience is None:
            raise HTTPException(status_code=404, detail="Experience not found")
        project_name = project_name.strip()
        if not project_name:
            return templates.TemplateResponse(
                request,
                "experience_detail.html",
                {
                    "experience": experience,
                    "projects": repo.list_projects(experience_id),
                    "error": "Project name is required.",
                },
                status_code=400,
            )
        project = Project(
            id=_new_id(),
            experience_id=experience_id,
            project_name=project_name,
            problem=problem.strip() or None,
            business_context=business_context.strip() or None,
            users_or_stakeholders=users_or_stakeholders.strip() or None,
            personal_role=personal_role.strip() or None,
            responsibilities=_split_lines(responsibilities),
            project_stage=project_stage.strip() or None,
            timeline=timeline.strip() or None,
            status=status.strip() or None,
        )
        repo.create_project(project)
        return _redirect(
            f"/experiences/{experience_id}",
            flash=f"Added project: {project.project_name}",
        )

    @app.get("/projects/{project_id}")
    def project_detail(request: Request, project_id: str):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        experience = repo.get_experience(project.experience_id)
        leaf_sections = [
            (
                "Contributions",
                [_leaf_fields(item) for item in repo.list_contributions(project_id)],
            ),
            ("Results", [_leaf_fields(item) for item in repo.list_results(project_id)]),
            (
                "Skill evidence",
                [_leaf_fields(item) for item in repo.list_skill_evidence(project_id)],
            ),
            ("Stories", [_leaf_fields(item) for item in repo.list_stories(project_id)]),
        ]
        open_questions = [
            question
            for question in repo.list_open_questions(status=None)
            if question.related_entity_type == "project"
            and question.related_entity_id == project_id
        ]
        return templates.TemplateResponse(
            request,
            "project_detail.html",
            {
                "project": project,
                "experience": experience,
                "leaf_sections": leaf_sections,
                "open_questions": open_questions,
            },
        )

    @app.post("/projects/{project_id}/notes")
    def import_notes(project_id: str, notes: str = Form(...)):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        notes_text = notes.strip()
        if not notes_text:
            return _redirect(f"/projects/{project_id}", flash="Notes were empty; nothing imported.")
        try:
            agent = build_agent(repo)
            result = agent.extract_from_notes(notes_text, project_id=project_id)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as a flash message
            return _redirect(f"/projects/{project_id}", flash=f"Import failed: {exc}")
        created = sum(result.get("created", {}).values())
        updated = sum(result.get("updated", {}).values())
        conflicts = len(result.get("conflicts", []))
        message = f"Import complete — created {created}, updated {updated}, conflicts {conflicts}."
        return _redirect(f"/projects/{project_id}", flash=message)

    @app.get("/open-questions")
    def open_questions(request: Request):
        repo = get_repo()
        questions = repo.list_open_questions(status="open")
        return templates.TemplateResponse(
            request,
            "open_questions.html",
            {"questions": questions},
        )

    return app


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)
