"""Minimal local FastAPI UI for browsing and building the career knowledge base.

Functional local-tool aesthetic: plain HTML, tables and forms, no styling
frameworks. Each request opens its own SQLite connection scoped to the
configured database path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from ..agents import CareerKnowledgeBuilderAgent
from ..ai_builder import AIBuilderClient
from ..completeness import CompletenessReport, GapItem, evaluate_project_completeness
from ..config import load_settings
from ..models import Contribution, Experience, Project, Result, SkillEvidence, Story
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


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for line in value.splitlines():
        for part in line.split(","):
            stripped = part.strip()
            if stripped:
                items.append(stripped)
    return items


@dataclass(frozen=True)
class LeafFieldDef:
    name: str
    label: str
    field_type: str = "text"


_LEAF_TABS = frozenset({"contributions", "results", "skills", "stories"})

_LEAF_FIELD_DEFS: dict[str, list[LeafFieldDef]] = {
    "contributions": [
        LeafFieldDef("action", "Action"),
        LeafFieldDef("technical_method", "Technical method"),
        LeafFieldDef("decision_made", "Decision made"),
        LeafFieldDef("difficulty", "Difficulty"),
        LeafFieldDef("alternative_considered", "Alternative considered"),
        LeafFieldDef("collaborators", "Collaborators", "list"),
        LeafFieldDef("ownership_level", "Ownership level"),
    ],
    "results": [
        LeafFieldDef("result_type", "Result type"),
        LeafFieldDef("metric_name", "Metric name"),
        LeafFieldDef("baseline", "Baseline"),
        LeafFieldDef("final_value", "Final value"),
        LeafFieldDef("absolute_change", "Absolute change"),
        LeafFieldDef("relative_change", "Relative change"),
        LeafFieldDef("business_impact", "Business impact", "textarea"),
        LeafFieldDef("confidence_level", "Confidence level"),
        LeafFieldDef("measurement_method", "Measurement method"),
        LeafFieldDef("is_estimate", "Is estimate", "bool"),
    ],
    "skills": [
        LeafFieldDef("skill", "Skill"),
        LeafFieldDef("proficiency", "Proficiency"),
        LeafFieldDef("evidence", "Evidence", "textarea"),
        LeafFieldDef("recency", "Recency"),
        LeafFieldDef("frequency", "Frequency"),
        LeafFieldDef("independently_used", "Independently used", "bool"),
    ],
    "stories": [
        LeafFieldDef("competency", "Competency"),
        LeafFieldDef("situation", "Situation", "textarea"),
        LeafFieldDef("task", "Task", "textarea"),
        LeafFieldDef("action", "Action", "textarea"),
        LeafFieldDef("result", "Result", "textarea"),
        LeafFieldDef("conflict", "Conflict", "textarea"),
        LeafFieldDef("lesson", "Lesson", "textarea"),
        LeafFieldDef("what_you_would_change", "What you would change", "textarea"),
    ],
}


def _form_value(values: list[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def _optional_str(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _parse_bool(value: str) -> bool | None:
    stripped = value.strip().lower()
    if not stripped:
        return None
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    return None


def _list_leaf_entities(repo: CareerRepository, project_id: str, tab: str) -> list[Any]:
    if tab == "contributions":
        return repo.list_contributions(project_id)
    if tab == "results":
        return repo.list_results(project_id)
    if tab == "skills":
        return repo.list_skill_evidence(project_id)
    return repo.list_stories(project_id)


def _leaf_row_count(form: Any, tab: str) -> int:
    counts = [len(form.getlist(field.name)) for field in _LEAF_FIELD_DEFS[tab]]
    counts.append(len(form.getlist("id")))
    return max(counts) if counts else 0


def _row_is_blank(form: Any, tab: str, index: int) -> bool:
    for field in _LEAF_FIELD_DEFS[tab]:
        if field.field_type == "bool":
            continue
        if _form_value(form.getlist(field.name), index).strip():
            return False
    return True


def _save_contributions(repo: CareerRepository, project_id: str, form: Any) -> None:
    delete_ids = set(form.getlist("delete_ids"))
    for contribution_id in delete_ids:
        repo.delete_contribution(contribution_id)

    ids = form.getlist("id")
    actions = form.getlist("action")
    technical_methods = form.getlist("technical_method")
    decisions = form.getlist("decision_made")
    difficulties = form.getlist("difficulty")
    alternatives = form.getlist("alternative_considered")
    collaborators = form.getlist("collaborators")
    ownership_levels = form.getlist("ownership_level")

    for index in range(_leaf_row_count(form, "contributions")):
        row_id = _form_value(ids, index).strip()
        action = _form_value(actions, index).strip()
        if row_id:
            if row_id in delete_ids:
                continue
            existing = repo.get_contribution(row_id)
            if existing is None:
                continue
            repo.update_contribution(
                replace(
                    existing,
                    action=action or existing.action,
                    technical_method=_optional_str(_form_value(technical_methods, index)),
                    decision_made=_optional_str(_form_value(decisions, index)),
                    difficulty=_optional_str(_form_value(difficulties, index)),
                    alternative_considered=_optional_str(_form_value(alternatives, index)),
                    collaborators=_split_list(_form_value(collaborators, index)),
                    ownership_level=_optional_str(_form_value(ownership_levels, index)),
                )
            )
            continue
        if not action:
            continue
        repo.create_contribution(
            Contribution(
                id=_new_id(),
                project_id=project_id,
                action=action,
                technical_method=_optional_str(_form_value(technical_methods, index)),
                decision_made=_optional_str(_form_value(decisions, index)),
                difficulty=_optional_str(_form_value(difficulties, index)),
                alternative_considered=_optional_str(_form_value(alternatives, index)),
                collaborators=_split_list(_form_value(collaborators, index)),
                ownership_level=_optional_str(_form_value(ownership_levels, index)),
            )
        )


def _save_results(repo: CareerRepository, project_id: str, form: Any) -> None:
    delete_ids = set(form.getlist("delete_ids"))
    for result_id in delete_ids:
        repo.delete_result(result_id)

    ids = form.getlist("id")
    for index in range(_leaf_row_count(form, "results")):
        row_id = _form_value(ids, index).strip()
        values = {
            field.name: form.getlist(field.name) for field in _LEAF_FIELD_DEFS["results"]
        }
        if row_id:
            if row_id in delete_ids:
                continue
            existing = repo.get_result(row_id)
            if existing is None:
                continue
            repo.update_result(
                replace(
                    existing,
                    result_type=_optional_str(_form_value(values["result_type"], index)),
                    metric_name=_optional_str(_form_value(values["metric_name"], index)),
                    baseline=_optional_str(_form_value(values["baseline"], index)),
                    final_value=_optional_str(_form_value(values["final_value"], index)),
                    absolute_change=_optional_str(_form_value(values["absolute_change"], index)),
                    relative_change=_optional_str(_form_value(values["relative_change"], index)),
                    business_impact=_optional_str(_form_value(values["business_impact"], index)),
                    confidence_level=_optional_str(_form_value(values["confidence_level"], index)),
                    measurement_method=_optional_str(
                        _form_value(values["measurement_method"], index)
                    ),
                    is_estimate=_parse_bool(_form_value(values["is_estimate"], index)) or False,
                )
            )
            continue
        if _row_is_blank(form, "results", index):
            continue
        repo.create_result(
            Result(
                id=_new_id(),
                project_id=project_id,
                result_type=_optional_str(_form_value(values["result_type"], index)),
                metric_name=_optional_str(_form_value(values["metric_name"], index)),
                baseline=_optional_str(_form_value(values["baseline"], index)),
                final_value=_optional_str(_form_value(values["final_value"], index)),
                absolute_change=_optional_str(_form_value(values["absolute_change"], index)),
                relative_change=_optional_str(_form_value(values["relative_change"], index)),
                business_impact=_optional_str(_form_value(values["business_impact"], index)),
                confidence_level=_optional_str(_form_value(values["confidence_level"], index)),
                measurement_method=_optional_str(
                    _form_value(values["measurement_method"], index)
                ),
                is_estimate=_parse_bool(_form_value(values["is_estimate"], index)) or False,
            )
        )


def _save_skills(repo: CareerRepository, project_id: str, form: Any) -> None:
    delete_ids = set(form.getlist("delete_ids"))
    for evidence_id in delete_ids:
        repo.delete_skill_evidence(evidence_id)

    ids = form.getlist("id")
    skills = form.getlist("skill")
    proficiencies = form.getlist("proficiency")
    evidences = form.getlist("evidence")
    recencies = form.getlist("recency")
    frequencies = form.getlist("frequency")
    independently_used = form.getlist("independently_used")

    for index in range(_leaf_row_count(form, "skills")):
        row_id = _form_value(ids, index).strip()
        skill = _form_value(skills, index).strip()
        if row_id:
            if row_id in delete_ids:
                continue
            existing = repo.get_skill_evidence(row_id)
            if existing is None:
                continue
            repo.update_skill_evidence(
                replace(
                    existing,
                    skill=skill or existing.skill,
                    proficiency=_optional_str(_form_value(proficiencies, index)),
                    evidence=_optional_str(_form_value(evidences, index)),
                    recency=_optional_str(_form_value(recencies, index)),
                    frequency=_optional_str(_form_value(frequencies, index)),
                    independently_used=_parse_bool(_form_value(independently_used, index)),
                )
            )
            continue
        if not skill:
            continue
        repo.create_skill_evidence(
            SkillEvidence(
                id=_new_id(),
                project_id=project_id,
                skill=skill,
                proficiency=_optional_str(_form_value(proficiencies, index)),
                evidence=_optional_str(_form_value(evidences, index)),
                recency=_optional_str(_form_value(recencies, index)),
                frequency=_optional_str(_form_value(frequencies, index)),
                independently_used=_parse_bool(_form_value(independently_used, index)),
            )
        )


def _save_stories(repo: CareerRepository, project_id: str, form: Any) -> None:
    delete_ids = set(form.getlist("delete_ids"))
    for story_id in delete_ids:
        repo.delete_story(story_id)

    ids = form.getlist("id")
    for index in range(_leaf_row_count(form, "stories")):
        row_id = _form_value(ids, index).strip()
        values = {field.name: form.getlist(field.name) for field in _LEAF_FIELD_DEFS["stories"]}
        if row_id:
            if row_id in delete_ids:
                continue
            existing = repo.get_story(row_id)
            if existing is None:
                continue
            repo.update_story(
                replace(
                    existing,
                    competency=_optional_str(_form_value(values["competency"], index)),
                    situation=_optional_str(_form_value(values["situation"], index)),
                    task=_optional_str(_form_value(values["task"], index)),
                    action=_optional_str(_form_value(values["action"], index)),
                    result=_optional_str(_form_value(values["result"], index)),
                    conflict=_optional_str(_form_value(values["conflict"], index)),
                    lesson=_optional_str(_form_value(values["lesson"], index)),
                    what_you_would_change=_optional_str(
                        _form_value(values["what_you_would_change"], index)
                    ),
                )
            )
            continue
        if _row_is_blank(form, "stories", index):
            continue
        repo.create_story(
            Story(
                id=_new_id(),
                project_id=project_id,
                competency=_optional_str(_form_value(values["competency"], index)),
                situation=_optional_str(_form_value(values["situation"], index)),
                task=_optional_str(_form_value(values["task"], index)),
                action=_optional_str(_form_value(values["action"], index)),
                result=_optional_str(_form_value(values["result"], index)),
                conflict=_optional_str(_form_value(values["conflict"], index)),
                lesson=_optional_str(_form_value(values["lesson"], index)),
                what_you_would_change=_optional_str(
                    _form_value(values["what_you_would_change"], index)
                ),
            )
        )


async def _save_leaf_tab(
    repo: CareerRepository,
    project_id: str,
    tab: str,
    form: Any,
) -> None:
    if tab == "contributions":
        _save_contributions(repo, project_id, form)
    elif tab == "results":
        _save_results(repo, project_id, form)
    elif tab == "skills":
        _save_skills(repo, project_id, form)
    elif tab == "stories":
        _save_stories(repo, project_id, form)


def _render_leaves_read(
    request: Request,
    repo: CareerRepository,
    project_id: str,
    tab: str,
    *,
    q: str | None = None,
) -> Any:
    project, experience, counts = _load_project_context(repo, project_id)
    items = [asdict(item) for item in _list_leaf_entities(repo, project_id, tab)]
    return templates.TemplateResponse(
        request,
        "partials/center_leaves_read.html",
        {
            "project": project,
            "experience": experience,
            "counts": counts,
            "active_tab": tab,
            "items": items,
            "field_defs": _LEAF_FIELD_DEFS[tab],
            **_right_panel_context(repo, project),
            **_tree_template_context(
                repo,
                q=q,
                selected_project_id=project_id,
            ),
        },
    )


def _render_leaves_edit(
    request: Request,
    repo: CareerRepository,
    project_id: str,
    tab: str,
) -> Any:
    project, experience, counts = _load_project_context(repo, project_id)
    items = [asdict(item) for item in _list_leaf_entities(repo, project_id, tab)]
    return templates.TemplateResponse(
        request,
        "partials/center_leaves_edit.html",
        {
            "project": project,
            "experience": experience,
            "counts": counts,
            "active_tab": tab,
            "items": items,
            "field_defs": _LEAF_FIELD_DEFS[tab],
        },
    )


def _redirect(url: str, *, flash: str | None = None) -> RedirectResponse:
    if flash:
        url = f"{url}?flash={quote(flash)}"
    return RedirectResponse(url, status_code=303)


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _tree_data(
    repo: CareerRepository,
    q: str | None = None,
) -> tuple[list[Experience], dict[str, list[Project]]]:
    experiences = repo.list_experiences()
    projects_by_experience = {
        experience.id: repo.list_projects(experience.id) for experience in experiences
    }
    if not q or not q.strip():
        return experiences, projects_by_experience

    needle = q.strip().lower()
    filtered_experiences: list[Experience] = []
    filtered_projects: dict[str, list[Project]] = {}
    for experience in experiences:
        projects = projects_by_experience.get(experience.id, [])
        experience_match = (
            needle in experience.organization.lower() or needle in experience.title.lower()
        )
        matching_projects = [
            project for project in projects if needle in project.project_name.lower()
        ]
        if experience_match:
            filtered_experiences.append(experience)
            filtered_projects[experience.id] = projects
        elif matching_projects:
            filtered_experiences.append(experience)
            filtered_projects[experience.id] = matching_projects
    return filtered_experiences, filtered_projects


def _project_counts(repo: CareerRepository, project_id: str) -> dict[str, int]:
    return {
        "contributions": len(repo.list_contributions(project_id)),
        "results": len(repo.list_results(project_id)),
        "skills": len(repo.list_skill_evidence(project_id)),
        "stories": len(repo.list_stories(project_id)),
    }


def _load_project_context(
    repo: CareerRepository,
    project_id: str,
) -> tuple[Project, Experience, dict[str, int]]:
    project = repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    experience = repo.get_experience(project.experience_id)
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    return project, experience, _project_counts(repo, project_id)


def _right_panel_context(
    repo: CareerRepository,
    project: Project | None,
) -> dict[str, CompletenessReport | None]:
    if project is None:
        return {"completeness": None}
    project_id = project.id
    return {
        "completeness": evaluate_project_completeness(
            project=project,
            contributions=repo.list_contributions(project_id),
            results=repo.list_results(project_id),
            skills=repo.list_skill_evidence(project_id),
            stories=repo.list_stories(project_id),
            open_questions=repo.list_open_questions(status="open"),
            dismissed_keys=repo.list_dismissed_gap_keys(project_id),
        ),
    }


def _render_overview_read(
    request: Request,
    repo: CareerRepository,
    project_id: str,
    *,
    q: str | None = None,
) -> Any:
    project, experience, counts = _load_project_context(repo, project_id)
    return templates.TemplateResponse(
        request,
        "partials/center_overview_read.html",
        {
            "project": project,
            "experience": experience,
            "counts": counts,
            "active_tab": "overview",
            **_right_panel_context(repo, project),
            **_tree_template_context(
                repo,
                q=q,
                selected_project_id=project_id,
            ),
        },
    )


def _render_notes_import_response(
    request: Request,
    repo: CareerRepository,
    project_id: str,
    *,
    message: str,
) -> Any:
    project, experience, counts = _load_project_context(repo, project_id)
    return templates.TemplateResponse(
        request,
        "partials/notes_import_response.html",
        {
            "project": project,
            "experience": experience,
            "counts": counts,
            "active_tab": "overview",
            "message": message,
            **_right_panel_context(repo, project),
        },
    )


def _render_right_panel(
    request: Request,
    repo: CareerRepository,
    project_id: str,
    *,
    message: str | None = None,
    expanded_gap_key: str | None = None,
) -> Any:
    project = repo.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return templates.TemplateResponse(
        request,
        "partials/right_notes.html",
        {
            "project": project,
            "message": message,
            "expanded_gap_key": expanded_gap_key,
            **_right_panel_context(repo, project),
        },
    )


def _gap_for_key(repo: CareerRepository, project: Project, gap_key: str) -> GapItem | None:
    report = _right_panel_context(repo, project)["completeness"]
    assert report is not None
    return next((gap for gap in report.checklist if gap.key == gap_key), None)


def _update_leaf_field(repo: CareerRepository, gap: GapItem, answer: str) -> bool:
    if gap.entity_id is None or gap.field_name is None:
        return False
    if gap.entity_type == "contribution":
        entity = repo.get_contribution(gap.entity_id)
        if entity is not None:
            repo.update_contribution(replace(entity, **{gap.field_name: answer}))
            return True
    elif gap.entity_type == "result":
        entity = repo.get_result(gap.entity_id)
        if entity is not None:
            repo.update_result(replace(entity, **{gap.field_name: answer}))
            return True
    elif gap.entity_type == "skill_evidence":
        entity = repo.get_skill_evidence(gap.entity_id)
        if entity is not None:
            repo.update_skill_evidence(replace(entity, **{gap.field_name: answer}))
            return True
    return False


def _render_gap_answer_response(
    request: Request,
    repo: CareerRepository,
    project_id: str,
    gap: GapItem,
) -> Any:
    project, experience, counts = _load_project_context(repo, project_id)
    if gap.kind == "overview_field":
        active_tab = "overview"
        items: list[dict[str, Any]] = []
        field_defs: list[LeafFieldDef] = []
    else:
        active_tab = (
            {
                "coverage.contributions": "contributions",
                "coverage.results": "results",
                "coverage.skills": "skills",
                "coverage.stories": "stories",
            }.get(gap.key)
            if gap.kind == "coverage"
            else {
                "contribution": "contributions",
                "result": "results",
                "skill_evidence": "skills",
                "story": "stories",
            }.get(gap.entity_type or "", "overview")
        )
        active_tab = active_tab or "overview"
        items = (
            [asdict(item) for item in _list_leaf_entities(repo, project_id, active_tab)]
            if active_tab in _LEAF_TABS
            else []
        )
        field_defs = _LEAF_FIELD_DEFS.get(active_tab, [])
    return templates.TemplateResponse(
        request,
        "partials/gap_answer_response.html",
        {
            "project": project,
            "experience": experience,
            "counts": counts,
            "active_tab": active_tab,
            "items": items,
            "field_defs": field_defs,
            **_right_panel_context(repo, project),
        },
    )


def _render_overview_edit(
    request: Request,
    repo: CareerRepository,
    project_id: str,
) -> Any:
    project, experience, counts = _load_project_context(repo, project_id)
    return templates.TemplateResponse(
        request,
        "partials/center_overview_edit.html",
        {
            "project": project,
            "experience": experience,
            "counts": counts,
            "active_tab": "overview",
        },
    )


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


def _render_tree(
    request: Request,
    repo: CareerRepository,
    *,
    q: str | None = None,
    selected_project_id: str | None = None,
) -> Any:
    return templates.TemplateResponse(
        request,
        "partials/tree.html",
        _tree_template_context(repo, q=q, selected_project_id=selected_project_id),
    )


def create_app(db_path: Path | None = None) -> FastAPI:
    resolved_path = db_path if db_path is not None else DB_PATH
    app = FastAPI(title="Career Agent")
    app.state.db_path = resolved_path

    def get_repo() -> CareerRepository:
        return CareerRepository(app.state.db_path)

    @app.get("/")
    def home(request: Request):
        repo = get_repo()
        experiences, projects_by_experience = _tree_data(repo)
        return templates.TemplateResponse(
            request,
            "workspace.html",
            {
                "experiences": experiences,
                "projects_by_experience": projects_by_experience,
                "selected_project_id": "",
            },
        )

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

    @app.get("/partials/add-experience")
    def partial_add_experience(
        request: Request,
        selected_project_id: str = "",
    ):
        return templates.TemplateResponse(
            request,
            "partials/add_experience_form.html",
            {"selected_project_id": selected_project_id},
        )

    @app.get("/partials/experiences/{experience_id}/add-project")
    def partial_add_project(
        request: Request,
        experience_id: str,
        selected_project_id: str = "",
    ):
        repo = get_repo()
        experience = repo.get_experience(experience_id)
        if experience is None:
            raise HTTPException(status_code=404, detail="Experience not found")
        return templates.TemplateResponse(
            request,
            "partials/add_project_form.html",
            {
                "experience": experience,
                "selected_project_id": selected_project_id,
            },
        )

    @app.get("/partials/projects/{project_id}")
    def partial_project(
        request: Request,
        project_id: str,
        tab: str = "overview",
        q: str = "",
    ):
        if tab == "overview":
            return _render_overview_read(
                request,
                get_repo(),
                project_id,
                q=q or None,
            )
        if tab in _LEAF_TABS:
            return _render_leaves_read(
                request,
                get_repo(),
                project_id,
                tab,
                q=q or None,
            )
        raise HTTPException(status_code=404, detail="Tab not found")

    @app.get("/partials/projects/{project_id}/edit")
    def partial_project_edit(
        request: Request,
        project_id: str,
        tab: str = "overview",
    ):
        if tab == "overview":
            return _render_overview_edit(request, get_repo(), project_id)
        if tab in _LEAF_TABS:
            return _render_leaves_edit(request, get_repo(), project_id, tab)
        raise HTTPException(status_code=404, detail="Tab not found")

    @app.post("/partials/projects/{project_id}")
    async def save_project_partial(
        request: Request,
        project_id: str,
        tab: str = "overview",
        problem: str = Form(""),
        business_context: str = Form(""),
        personal_role: str = Form(""),
        users_or_stakeholders: str = Form(""),
        responsibilities: str = Form(""),
        project_stage: str = Form(""),
        timeline: str = Form(""),
        status: str = Form(""),
    ):
        repo = get_repo()
        if tab in _LEAF_TABS:
            project = repo.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            form = await request.form()
            await _save_leaf_tab(repo, project_id, tab, form)
            return _render_leaves_read(request, repo, project_id, tab)
        if tab != "overview":
            raise HTTPException(status_code=404, detail="Tab not found")
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        updated = replace(
            project,
            problem=problem.strip() or None,
            business_context=business_context.strip() or None,
            personal_role=personal_role.strip() or None,
            users_or_stakeholders=users_or_stakeholders.strip() or None,
            responsibilities=_split_lines(responsibilities),
            project_stage=project_stage.strip() or None,
            timeline=timeline.strip() or None,
            status=status.strip() or None,
        )
        repo.update_project(updated)
        return _render_overview_read(request, repo, project_id)

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
        selected_project_id: str = Form(""),
    ):
        repo = get_repo()
        organization = organization.strip()
        title = title.strip()
        if not organization or not title:
            if _is_htmx(request):
                return templates.TemplateResponse(
                    request,
                    "partials/add_experience_form.html",
                    {
                        "error": "Organization and title are required.",
                        "organization": organization,
                        "title": title,
                        "start_date": start_date.strip(),
                        "selected_project_id": selected_project_id,
                    },
                    status_code=400,
                )
            return templates.TemplateResponse(
                request,
                "partials/add_experience_form.html",
                {
                    "error": "Organization and title are required.",
                    "organization": organization,
                    "title": title,
                    "start_date": start_date.strip(),
                    "selected_project_id": selected_project_id,
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
        if _is_htmx(request):
            return _render_tree(request, repo)
        return _redirect("/", flash=f"Added experience: {experience.organization} — {experience.title}")

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
        selected_project_id: str = Form(""),
    ):
        repo = get_repo()
        experience = repo.get_experience(experience_id)
        if experience is None:
            raise HTTPException(status_code=404, detail="Experience not found")
        project_name = project_name.strip()
        if not project_name:
            if _is_htmx(request):
                return templates.TemplateResponse(
                    request,
                    "partials/add_project_form.html",
                    {
                        "experience": experience,
                        "error": "Project name is required.",
                        "project_name": project_name,
                        "selected_project_id": selected_project_id,
                    },
                    status_code=400,
                )
            return templates.TemplateResponse(
                request,
                "partials/add_project_form.html",
                {
                    "experience": experience,
                    "error": "Project name is required.",
                    "project_name": project_name,
                    "selected_project_id": selected_project_id,
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
        if _is_htmx(request):
            return _render_tree(request, repo)
        return _redirect("/", flash=f"Added project: {project.project_name}")

    @app.post("/projects/{project_id}/notes")
    def import_notes(request: Request, project_id: str, notes: str = Form(...)):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        notes_text = notes.strip()
        if not notes_text:
            message = "Notes were empty; nothing imported."
            if _is_htmx(request):
                return _render_notes_import_response(request, repo, project_id, message=message)
            return _redirect("/", flash=message)
        try:
            agent = build_agent(repo)
            result = agent.extract_from_notes(notes_text, project_id=project_id)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as a flash message
            message = f"Import failed: {exc}"
            if _is_htmx(request):
                return _render_notes_import_response(request, repo, project_id, message=message)
            return _redirect("/", flash=message)
        created = sum(result.get("created", {}).values())
        updated = sum(result.get("updated", {}).values())
        conflicts = len(result.get("conflicts", []))
        message = f"Import complete — created {created}, updated {updated}, conflicts {conflicts}."
        if _is_htmx(request):
            return _render_notes_import_response(request, repo, project_id, message=message)
        return _redirect("/", flash=message)

    @app.post("/projects/{project_id}/gaps/unknown")
    def mark_gap_unknown(
        request: Request,
        project_id: str,
        gap_key: str = Form(...),
    ):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        gap = _gap_for_key(repo, project, gap_key)
        if gap is None:
            return _render_right_panel(
                request, repo, project_id, message="That missing item is no longer available."
            )
        if gap.kind == "open_question" and gap.open_question_id:
            question = next(
                (
                    question
                    for question in repo.list_open_questions(status="open")
                    if question.id == gap.open_question_id
                ),
                None,
            )
            if question is None:
                return _render_right_panel(
                    request, repo, project_id, message="That question is no longer available."
                )
            repo.update_open_question(replace(question, status="dismissed"))
        else:
            repo.dismiss_gap(project_id, gap.key)
        return _render_right_panel(request, repo, project_id)

    @app.get("/projects/{project_id}/gaps/answer-form")
    def gap_answer_form(
        request: Request,
        project_id: str,
        gap_key: str,
        cancel: bool = False,
    ):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if _gap_for_key(repo, project, gap_key) is None:
            return _render_right_panel(
                request, repo, project_id, message="That missing item is no longer available."
            )
        return _render_right_panel(
            request,
            repo,
            project_id,
            expanded_gap_key=None if cancel else gap_key,
        )

    @app.post("/projects/{project_id}/gaps/answer")
    def answer_gap(
        request: Request,
        project_id: str,
        gap_key: str = Form(...),
        answer: str = Form(...),
    ):
        repo = get_repo()
        project = repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        gap = _gap_for_key(repo, project, gap_key)
        answer = answer.strip()
        if gap is None:
            return _render_right_panel(
                request, repo, project_id, message="That missing item is no longer available."
            )
        if not answer:
            return _render_right_panel(
                request,
                repo,
                project_id,
                message="Please enter an answer.",
                expanded_gap_key=gap_key,
            )
        try:
            if gap.kind == "overview_field" and gap.field_name:
                repo.update_project(replace(project, **{gap.field_name: answer}))
            elif gap.kind == "leaf_field":
                if not _update_leaf_field(repo, gap, answer):
                    raise ValueError("The related record no longer exists.")
            elif gap.kind == "coverage":
                build_agent(repo).extract_from_notes(answer, project_id=project_id)
            elif gap.kind == "open_question" and gap.open_question_id:
                question = next(
                    (
                        question
                        for question in repo.list_open_questions(status="open")
                        if question.id == gap.open_question_id
                    ),
                    None,
                )
                if question is None:
                    raise ValueError("That question is no longer available.")
                build_agent(repo).extract_from_notes(
                    f"Question: {question.question}\nAnswer: {answer}",
                    project_id=project_id,
                )
                repo.update_open_question(replace(question, status="resolved"))
            else:
                raise ValueError("This missing item cannot be answered.")
        except Exception as exc:  # noqa: BLE001 - surfaced to the user in the right panel
            return _render_right_panel(
                request,
                repo,
                project_id,
                message=f"Answer failed: {exc}",
                expanded_gap_key=gap_key,
            )
        return _render_gap_answer_response(request, repo, project_id, gap)

    return app


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)
