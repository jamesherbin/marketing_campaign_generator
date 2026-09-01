from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Phase(str, Enum):
    PLANNING = "planning"
    DEVELOPMENT = "development"
    EXECUTION = "execution"
    MONITORING = "monitoring"


PHASE_ORDER = [Phase.PLANNING, Phase.DEVELOPMENT, Phase.EXECUTION, Phase.MONITORING]


class PhaseStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class CampaignBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(min_length=1, max_length=200)
    campaign_goal: str = Field(min_length=1)
    target_audience: list[str] = Field(min_length=1)
    duration_weeks: int = Field(gt=0, le=260)
    budget: float = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    preferred_channels: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    industry: str | None = None
    product: str | None = None
    constraints: list[str] = Field(default_factory=list)


class PlanningOutput(BaseModel):
    goals: list[str]
    measurable_objectives: list[str]
    audience_segments: list[str]
    positioning_statement: str
    value_proposition: str
    key_messages: list[str]
    recommended_channels: list[str]
    budget_by_channel: dict[str, float]


class ContentAsset(BaseModel):
    asset_id: UUID = Field(default_factory=uuid4)
    channel: str
    format: str
    headline: str
    body: str
    call_to_action: str | None = None
    status: str = "draft"


class DevelopmentOutput(BaseModel):
    creative_direction: str
    assets: list[ContentAsset]
    media_plan: dict[str, Any]


class ScheduledActivity(BaseModel):
    channel: str
    action: str
    scheduled_for: datetime | None = None
    status: str = "prepared"


class ExecutionOutput(BaseModel):
    activities: list[ScheduledActivity]
    publication_summary: str


class MonitoringOutput(BaseModel):
    kpis: dict[str, float | int | str | None]
    analysis: list[str]
    recommendations: list[str]
    stakeholder_summary: str


class PhaseRun(BaseModel):
    status: PhaseStatus = PhaseStatus.NOT_STARTED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class ApprovalRecord(BaseModel):
    phase: Phase
    decision: ApprovalDecision
    actor: str = Field(min_length=1)
    comment: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)


class CampaignState(BaseModel):
    """Canonical state passed through every campaign lifecycle phase."""

    model_config = ConfigDict(validate_assignment=True)
    campaign_id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    status: CampaignStatus = CampaignStatus.DRAFT
    current_phase: Phase = Phase.PLANNING
    brief: CampaignBrief
    planning: PlanningOutput | None = None
    development: DevelopmentOutput | None = None
    execution: ExecutionOutput | None = None
    monitoring: MonitoringOutput | None = None
    phase_runs: dict[Phase, PhaseRun] = Field(
        default_factory=lambda: {phase: PhaseRun() for phase in PHASE_ORDER}
    )
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def ensure_all_phase_runs(self) -> "CampaignState":
        for phase in PHASE_ORDER:
            self.phase_runs.setdefault(phase, PhaseRun())
        return self


class CampaignCreate(BaseModel):
    brief: CampaignBrief
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    decision: ApprovalDecision
    comment: str | None = None
