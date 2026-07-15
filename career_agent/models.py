from __future__ import annotations

from dataclasses import dataclass, field

from .profile import now_iso


LEAF_TYPES = ("contribution", "result", "skill_evidence", "story")


@dataclass
class Experience:
    id: str
    organization: str
    title: str
    employment_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    team: str | None = None
    manager_level: str | None = None
    business_context: str | None = None
    reason_for_joining: str | None = None
    reason_for_leaving: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Project:
    id: str
    experience_id: str
    project_name: str
    problem: str | None = None
    business_context: str | None = None
    users_or_stakeholders: str | None = None
    personal_role: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    project_stage: str | None = None
    timeline: str | None = None
    status: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Contribution:
    id: str
    project_id: str
    action: str
    technical_method: str | None = None
    decision_made: str | None = None
    difficulty: str | None = None
    alternative_considered: str | None = None
    collaborators: list[str] = field(default_factory=list)
    ownership_level: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Result:
    id: str
    project_id: str
    result_type: str | None = None
    metric_name: str | None = None
    baseline: str | None = None
    final_value: str | None = None
    absolute_change: str | None = None
    relative_change: str | None = None
    business_impact: str | None = None
    confidence_level: str | None = None
    measurement_method: str | None = None
    is_estimate: bool = False
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class SkillEvidence:
    id: str
    project_id: str
    skill: str
    proficiency: str | None = None
    evidence: str | None = None
    recency: str | None = None
    frequency: str | None = None
    independently_used: bool | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class Story:
    id: str
    project_id: str
    competency: str | None = None
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    conflict: str | None = None
    lesson: str | None = None
    what_you_would_change: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class OpenQuestion:
    id: str
    related_entity_type: str
    related_entity_id: str
    question: str
    why_it_matters: str | None = None
    priority: str = "medium"
    status: str = "open"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
