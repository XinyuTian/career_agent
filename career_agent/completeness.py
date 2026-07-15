from __future__ import annotations

from dataclasses import dataclass

from .models import (
    Contribution,
    OpenQuestion,
    Project,
    Result,
    SkillEvidence,
    Story,
)


@dataclass(frozen=True)
class GapItem:
    key: str
    label: str
    kind: str  # overview_field | coverage | leaf_field | open_question
    passed: bool
    field_name: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    open_question_id: str | None = None


@dataclass(frozen=True)
class CompletenessReport:
    percent: int
    missing: list[GapItem]
    checklist: list[GapItem]


def _is_empty(value: str | None) -> bool:
    return not value or not value.strip()


def _overview_gaps(project: Project) -> list[GapItem]:
    fields = [
        ("overview.problem", "problem", "Problem not set"),
        ("overview.business_context", "business_context", "Business context not set"),
        ("overview.personal_role", "personal_role", "Your role not set"),
        (
            "overview.users_or_stakeholders",
            "users_or_stakeholders",
            "Stakeholders not set",
        ),
    ]
    gaps: list[GapItem] = []
    for key, field_name, label in fields:
        value = getattr(project, field_name)
        passed = not _is_empty(value)
        gaps.append(
            GapItem(
                key=key,
                label=label,
                kind="overview_field",
                passed=passed,
                field_name=field_name,
                entity_type="project",
                entity_id=project.id,
            )
        )
    return gaps


def _coverage_gaps(
    *,
    project_id: str,
    contributions: list[Contribution],
    results: list[Result],
    skills: list[SkillEvidence],
    stories: list[Story],
) -> list[GapItem]:
    checks = [
        (
            "coverage.contributions",
            len(contributions) > 0,
            "No contributions recorded",
        ),
        ("coverage.results", len(results) > 0, "No results recorded"),
        ("coverage.skills", len(skills) > 0, "No skill evidence recorded"),
        ("coverage.stories", len(stories) > 0, "No stories recorded"),
    ]
    return [
        GapItem(
            key=key,
            label=label,
            kind="coverage",
            passed=passed,
            entity_type="project",
            entity_id=project_id,
        )
        for key, passed, label in checks
    ]


def _leaf_gaps(
    *,
    contributions: list[Contribution],
    results: list[Result],
    skills: list[SkillEvidence],
) -> list[GapItem]:
    gaps: list[GapItem] = []
    for contribution in contributions:
        passed = not _is_empty(contribution.ownership_level)
        gaps.append(
            GapItem(
                key=f"contribution.{contribution.id}.ownership_level",
                label=f"Ownership unclear on: {contribution.action}",
                kind="leaf_field",
                passed=passed,
                field_name="ownership_level",
                entity_type="contribution",
                entity_id=contribution.id,
            )
        )
    for result in results:
        if _is_empty(result.metric_name):
            continue
        passed = not _is_empty(result.baseline)
        gaps.append(
            GapItem(
                key=f"result.{result.id}.baseline",
                label=f"No baseline for: {result.metric_name}",
                kind="leaf_field",
                passed=passed,
                field_name="baseline",
                entity_type="result",
                entity_id=result.id,
            )
        )
    for skill in skills:
        passed = not _is_empty(skill.evidence)
        gaps.append(
            GapItem(
                key=f"skill.{skill.id}.evidence",
                label=f"Skill evidence thin for: {skill.skill}",
                kind="leaf_field",
                passed=passed,
                field_name="evidence",
                entity_type="skill_evidence",
                entity_id=skill.id,
            )
        )
    return gaps


def _open_question_gaps(
    *,
    project_id: str,
    leaf_ids: set[str],
    open_questions: list[OpenQuestion],
) -> list[GapItem]:
    gaps: list[GapItem] = []
    for question in open_questions:
        if question.status != "open":
            continue
        related_id = question.related_entity_id
        if related_id != project_id and related_id not in leaf_ids:
            continue
        gaps.append(
            GapItem(
                key=f"open_question.{question.id}",
                label=question.question,
                kind="open_question",
                passed=False,
                open_question_id=question.id,
                entity_type=question.related_entity_type,
                entity_id=question.related_entity_id,
            )
        )
    return gaps


def evaluate_project_completeness(
    *,
    project: Project,
    contributions: list[Contribution],
    results: list[Result],
    skills: list[SkillEvidence],
    stories: list[Story],
    open_questions: list[OpenQuestion],
    dismissed_keys: set[str],
) -> CompletenessReport:
    leaf_ids = {
        *[c.id for c in contributions],
        *[r.id for r in results],
        *[s.id for s in skills],
        *[t.id for t in stories],
    }
    all_gaps = [
        *_overview_gaps(project),
        *_coverage_gaps(
            project_id=project.id,
            contributions=contributions,
            results=results,
            skills=skills,
            stories=stories,
        ),
        *_leaf_gaps(contributions=contributions, results=results, skills=skills),
        *_open_question_gaps(
            project_id=project.id,
            leaf_ids=leaf_ids,
            open_questions=open_questions,
        ),
    ]
    checklist = [g for g in all_gaps if g.key not in dismissed_keys]
    missing = [g for g in checklist if not g.passed]
    passed_count = len(checklist) - len(missing)
    percent = round(100 * passed_count / max(len(checklist), 1))
    return CompletenessReport(percent=percent, missing=missing, checklist=checklist)
