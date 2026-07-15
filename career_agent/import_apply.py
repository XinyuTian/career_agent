from __future__ import annotations

import uuid
from dataclasses import asdict, fields as dataclass_fields, replace
from typing import Any

from .merge import merge_record
from .models import (
    Contribution,
    Experience,
    OpenQuestion,
    Project,
    Result,
    SkillEvidence,
    Story,
)
from .repository import CareerRepository


_LIST_FIELDS_BY_MODEL: dict[type, set[str]] = {
    Project: {"responsibilities"},
    Contribution: {"collaborators"},
}

_LEAF_CONFIG: dict[str, dict[str, Any]] = {
    "contributions": {
        "entity_type": "contribution",
        "model": Contribution,
        "soft_key": "action",
        "get": "get_contribution",
        "create": "create_contribution",
        "update": "update_contribution",
        "list": "list_contributions",
    },
    "results": {
        "entity_type": "result",
        "model": Result,
        "soft_key": "metric_name",
        "get": "get_result",
        "create": "create_result",
        "update": "update_result",
        "list": "list_results",
    },
    "skill_evidence": {
        "entity_type": "skill_evidence",
        "model": SkillEvidence,
        "soft_key": "skill",
        "get": "get_skill_evidence",
        "create": "create_skill_evidence",
        "update": "update_skill_evidence",
        "list": "list_skill_evidence",
    },
    "stories": {
        "entity_type": "story",
        "model": Story,
        "soft_key": "competency",
        "get": "get_story",
        "create": "create_story",
        "update": "update_story",
        "list": "list_stories",
    },
}


def apply_import_payload(
    repo: CareerRepository,
    payload: dict[str, Any],
    *,
    project_id: str | None = None,
    experience_id: str | None = None,
) -> dict[str, Any]:
    """Apply a nested experiences -> projects -> leaves import payload."""
    scope_project = None
    if project_id is not None:
        scope_project = repo.get_project(project_id)
        if scope_project is None:
            raise ValueError(f"Unknown project_id: {project_id!r}")
    if experience_id is not None and repo.get_experience(experience_id) is None:
        raise ValueError(f"Unknown experience_id: {experience_id!r}")
    if (
        scope_project is not None
        and experience_id is not None
        and scope_project.experience_id != experience_id
    ):
        raise ValueError(
            f"project_id {project_id!r} does not belong to experience_id {experience_id!r}"
        )
    scoped_experience_id = (
        experience_id
        if experience_id is not None
        else scope_project.experience_id if scope_project is not None else None
    )

    result: dict[str, Any] = {
        "created": {},
        "updated": {},
        "open_questions": [],
        "conflicts": [],
    }

    repo.conn.execute("BEGIN")
    try:
        for experience_payload in payload.get("experiences", []):
            _apply_experience(
                repo,
                experience_payload,
                result,
                project_id=project_id,
                experience_id=scoped_experience_id,
            )
        for question_payload in payload.get("open_questions", []):
            _create_open_question(repo, question_payload, result)
    except Exception:
        repo.conn.execute("ROLLBACK")
        raise
    else:
        repo.conn.execute("COMMIT")

    return result


def _new_id() -> str:
    return str(uuid.uuid4())


def _model_field_names(model_type: type) -> set[str]:
    return {f.name for f in dataclass_fields(model_type)} - {
        "id",
        "created_at",
        "updated_at",
    }


def _filter_payload(model_type: type, payload: dict[str, Any]) -> dict[str, Any]:
    names = _model_field_names(model_type)
    return {key: value for key, value in payload.items() if key in names}


def _resolve_existing(key_match: Any, id_match: Any, incoming_id: str | None) -> tuple[Any, bool]:
    """Returns (existing_row_or_None, is_ambiguous_conflict)."""
    if key_match is not None:
        if incoming_id and key_match.id != incoming_id:
            return None, True
        return key_match, False
    if id_match is not None:
        return id_match, False
    return None, False


def _bump(bucket: dict[str, int], key: str) -> None:
    bucket[key] = bucket.get(key, 0) + 1


def _record_id_conflict(
    repo: CareerRepository,
    result: dict[str, Any],
    entity_type: str,
    incoming_id: str,
    existing_id: str,
) -> None:
    question = OpenQuestion(
        id=_new_id(),
        related_entity_type=entity_type,
        related_entity_id=existing_id,
        question=(
            f"Import referenced {entity_type} id={incoming_id!r}, but its exact-key "
            f"match resolves to existing id={existing_id!r}. Which record should this "
            "data belong to?"
        ),
        why_it_matters="Ambiguous identity between explicit id and matched key; no data was overwritten.",
        priority="high",
    )
    repo.create_open_question(question)
    entry = asdict(question)
    result["open_questions"].append(entry)
    result["conflicts"].append(entry)


def _record_parent_scope_conflict(
    repo: CareerRepository,
    result: dict[str, Any],
    entity_type: str,
    entity_id: str,
    parent_type: str,
    actual_parent_id: str,
    expected_parent_id: str,
) -> None:
    question = OpenQuestion(
        id=_new_id(),
        related_entity_type=entity_type,
        related_entity_id=entity_id,
        question=(
            f"Import nested {entity_type} id={entity_id!r} under {parent_type} "
            f"id={expected_parent_id!r}, but it belongs to id={actual_parent_id!r}. "
            "Which parent should this data belong to?"
        ),
        why_it_matters=(
            "The explicit id resolves outside the payload's parent scope; "
            "no data was overwritten."
        ),
        priority="high",
    )
    repo.create_open_question(question)
    entry = asdict(question)
    result["open_questions"].append(entry)
    result["conflicts"].append(entry)


def _record_field_conflicts(
    repo: CareerRepository,
    result: dict[str, Any],
    entity_type: str,
    entity_id: str,
    conflicts: list[str],
) -> None:
    for conflict in conflicts:
        field_name, _, detail = conflict.partition(": ")
        question = OpenQuestion(
            id=_new_id(),
            related_entity_type=entity_type,
            related_entity_id=entity_id,
            question=(
                f"Conflicting value for '{field_name}' on {entity_type} {entity_id}: {detail}"
            ),
            priority="medium",
        )
        repo.create_open_question(question)
        entry = asdict(question)
        result["open_questions"].append(entry)
        result["conflicts"].append(entry)


def _create_open_question(
    repo: CareerRepository,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    question = OpenQuestion(
        id=payload.get("id") or _new_id(),
        related_entity_type=payload["related_entity_type"],
        related_entity_id=payload["related_entity_id"],
        question=payload["question"],
        why_it_matters=payload.get("why_it_matters"),
        priority=payload.get("priority", "medium"),
    )
    repo.create_open_question(question)
    result["open_questions"].append(asdict(question))


def _apply_experience(
    repo: CareerRepository,
    payload: dict[str, Any],
    result: dict[str, Any],
    *,
    project_id: str | None,
    experience_id: str | None,
) -> None:
    fields_payload = {key: value for key, value in payload.items() if key != "projects"}
    incoming_id = fields_payload.get("id")

    key_match = repo.find_experience_by_key(
        fields_payload.get("organization"),
        fields_payload.get("title"),
        fields_payload.get("start_date"),
    )
    id_match = repo.get_experience(incoming_id) if incoming_id else None
    existing, is_conflict = _resolve_existing(key_match, id_match, incoming_id)

    if is_conflict:
        _record_id_conflict(repo, result, "experience", incoming_id, key_match.id)
        return

    if experience_id is not None:
        target_id = existing.id if existing is not None else None
        if target_id != experience_id:
            return

    if project_id is not None:
        current = existing
    elif existing is None:
        new_id = incoming_id or _new_id()
        kwargs = _filter_payload(Experience, fields_payload)
        current = Experience(id=new_id, **kwargs)
        repo.create_experience(current)
        _bump(result["created"], "experiences")
    else:
        existing_fields = _filter_payload(Experience, asdict(existing))
        incoming_fields = _filter_payload(Experience, fields_payload)
        merged, conflicts = merge_record(
            existing_fields,
            incoming_fields,
            list_fields=set(),
        )
        current = replace(existing, **merged)
        repo.update_experience(current)
        _bump(result["updated"], "experiences")
        _record_field_conflicts(repo, result, "experience", existing.id, conflicts)

    for project_payload in payload.get("projects", []):
        _apply_project(repo, project_payload, current.id, result, project_id=project_id)


def _apply_project(
    repo: CareerRepository,
    payload: dict[str, Any],
    experience_id_value: str,
    result: dict[str, Any],
    *,
    project_id: str | None,
) -> None:
    leaf_keys = set(_LEAF_CONFIG.keys())
    fields_payload = {key: value for key, value in payload.items() if key not in leaf_keys}
    incoming_id = fields_payload.get("id")

    key_match = repo.find_project_by_key(experience_id_value, fields_payload.get("project_name"))
    id_match = repo.get_project(incoming_id) if incoming_id else None
    if id_match is not None and id_match.experience_id != experience_id_value:
        _record_parent_scope_conflict(
            repo,
            result,
            "project",
            id_match.id,
            "experience",
            id_match.experience_id,
            experience_id_value,
        )
        return
    existing, is_conflict = _resolve_existing(key_match, id_match, incoming_id)

    if is_conflict:
        _record_id_conflict(repo, result, "project", incoming_id, key_match.id)
        return

    if project_id is not None:
        target_id = existing.id if existing is not None else None
        if target_id != project_id:
            return

    list_fields = _LIST_FIELDS_BY_MODEL.get(Project, set())

    if project_id is not None:
        current = existing
    elif existing is None:
        new_id = incoming_id or _new_id()
        kwargs = _filter_payload(Project, fields_payload)
        kwargs["experience_id"] = experience_id_value
        current = Project(id=new_id, **kwargs)
        repo.create_project(current)
        _bump(result["created"], "projects")
    else:
        existing_fields = _filter_payload(Project, asdict(existing))
        incoming_fields = _filter_payload(Project, fields_payload)
        merged, conflicts = merge_record(
            existing_fields,
            incoming_fields,
            list_fields=list_fields,
        )
        current = replace(existing, **merged)
        repo.update_project(current)
        _bump(result["updated"], "projects")
        _record_field_conflicts(repo, result, "project", existing.id, conflicts)

    for plural_key in _LEAF_CONFIG:
        for leaf_payload in payload.get(plural_key, []):
            _apply_leaf(repo, plural_key, leaf_payload, current.id, result)


def _apply_leaf(
    repo: CareerRepository,
    plural_key: str,
    payload: dict[str, Any],
    project_id_value: str,
    result: dict[str, Any],
) -> None:
    config = _LEAF_CONFIG[plural_key]
    model_type = config["model"]
    entity_type = config["entity_type"]
    soft_key = config["soft_key"]
    list_fn = getattr(repo, config["list"])
    get_fn = getattr(repo, config["get"])
    create_fn = getattr(repo, config["create"])
    update_fn = getattr(repo, config["update"])

    incoming_id = payload.get("id")
    soft_value = payload.get(soft_key)

    key_match = None
    if soft_value not in (None, ""):
        for item in list_fn(project_id_value):
            if getattr(item, soft_key) == soft_value:
                key_match = item
                break

    id_match = get_fn(incoming_id) if incoming_id else None
    if id_match is not None and id_match.project_id != project_id_value:
        _record_parent_scope_conflict(
            repo,
            result,
            entity_type,
            id_match.id,
            "project",
            id_match.project_id,
            project_id_value,
        )
        return
    existing, is_conflict = _resolve_existing(key_match, id_match, incoming_id)

    if is_conflict:
        _record_id_conflict(repo, result, entity_type, incoming_id, key_match.id)
        return

    list_fields = _LIST_FIELDS_BY_MODEL.get(model_type, set())

    if existing is None:
        new_id = incoming_id or _new_id()
        kwargs = _filter_payload(model_type, payload)
        kwargs["project_id"] = project_id_value
        entity = model_type(id=new_id, **kwargs)
        create_fn(entity)
        _bump(result["created"], plural_key)
        return

    existing_fields = _filter_payload(model_type, asdict(existing))
    incoming_fields = _filter_payload(model_type, payload)
    merged, conflicts = merge_record(
        existing_fields,
        incoming_fields,
        list_fields=list_fields,
    )
    before_text = repo.leaf_searchable_text(entity_type, existing.id)
    updated = replace(existing, **merged)
    update_fn(updated)
    _bump(result["updated"], plural_key)
    if repo.leaf_searchable_text(entity_type, existing.id) != before_text:
        repo.delete_embedding(entity_type, existing.id)
    _record_field_conflicts(repo, result, entity_type, existing.id, conflicts)
