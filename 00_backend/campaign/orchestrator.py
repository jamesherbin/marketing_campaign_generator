from datetime import timedelta
from typing import Protocol

from .models import (
    ApprovalDecision, ApprovalRecord, CampaignState, CampaignStatus, ContentAsset,
    DevelopmentOutput, ExecutionOutput, MonitoringOutput, PHASE_ORDER, Phase,
    PhaseStatus, PlanningOutput, ScheduledActivity, utc_now,
)
from .repository import InMemoryCampaignRepository


class InvalidTransitionError(ValueError):
    pass


class PhaseRunner(Protocol):
    async def run(self, campaign: CampaignState): ...


class PlanningRunner:
    async def run(self, campaign: CampaignState) -> PlanningOutput:
        brief = campaign.brief
        channels = brief.preferred_channels or ["social_media", "email", "digital_ads"]
        base_share = round(brief.budget / len(channels), 2)
        allocation = {channel: base_share for channel in channels}
        allocation[channels[-1]] = round(brief.budget - sum(allocation.values()) + base_share, 2)
        metrics = brief.success_metrics or ["reach", "engagement_rate", "conversions"]
        return PlanningOutput(
            goals=[brief.campaign_goal],
            measurable_objectives=[f"Improve {metric} during the {brief.duration_weeks}-week campaign" for metric in metrics],
            audience_segments=brief.target_audience,
            positioning_statement=f"{brief.brand} is the relevant choice for {', '.join(brief.target_audience)}.",
            value_proposition=f"{brief.brand} helps its audience achieve {brief.campaign_goal.lower()}.",
            key_messages=[brief.campaign_goal, f"Discover what makes {brief.brand} different"],
            recommended_channels=channels,
            budget_by_channel=allocation,
        )


class DevelopmentRunner:
    async def run(self, campaign: CampaignState) -> DevelopmentOutput:
        if campaign.planning is None:
            raise InvalidTransitionError("Planning must be completed before development")
        assets = [ContentAsset(
            channel=channel, format="campaign_concept",
            headline=campaign.planning.key_messages[0], body=campaign.planning.value_proposition,
            call_to_action=f"Learn more about {campaign.brief.brand}",
        ) for channel in campaign.planning.recommended_channels]
        return DevelopmentOutput(
            creative_direction=f"A consistent, audience-led campaign for {campaign.brief.brand}",
            assets=assets,
            media_plan={"duration_weeks": campaign.brief.duration_weeks,
                        "budget_by_channel": campaign.planning.budget_by_channel, "cadence": "weekly"},
        )


class ExecutionRunner:
    async def run(self, campaign: CampaignState) -> ExecutionOutput:
        if campaign.development is None:
            raise InvalidTransitionError("Development must be completed before execution")
        activities = [ScheduledActivity(
            channel=asset.channel, action=f"Publish {asset.format}: {asset.headline}",
            scheduled_for=utc_now() + timedelta(days=index),
        ) for index, asset in enumerate(campaign.development.assets)]
        return ExecutionOutput(
            activities=activities,
            publication_summary="Activities are prepared. External publication requires a channel integration.",
        )


class MonitoringRunner:
    async def run(self, campaign: CampaignState) -> MonitoringOutput:
        if campaign.execution is None:
            raise InvalidTransitionError("Execution must be completed before monitoring")
        return MonitoringOutput(
            kpis={metric: None for metric in campaign.brief.success_metrics},
            analysis=["No live channel metrics have been ingested yet."],
            recommendations=["Connect channel analytics and establish a reporting baseline."],
            stakeholder_summary="The campaign is prepared; performance reporting awaits live data.",
        )


class CampaignOrchestrator:
    def __init__(
        self,
        repository: InMemoryCampaignRepository,
        runners: dict[Phase, PhaseRunner] | None = None,
    ) -> None:
        self.repository = repository
        self.runners: dict[Phase, PhaseRunner] = runners or {
            Phase.PLANNING: PlanningRunner(), Phase.DEVELOPMENT: DevelopmentRunner(),
            Phase.EXECUTION: ExecutionRunner(), Phase.MONITORING: MonitoringRunner(),
        }

    async def run_phase(self, campaign: CampaignState, phase: Phase) -> CampaignState:
        expected = self._next_incomplete_phase(campaign)
        if expected != phase:
            raise InvalidTransitionError(f"Next runnable phase is {expected.value}, not {phase.value}")
        phase_run = campaign.phase_runs[phase]
        phase_run.status, phase_run.started_at, phase_run.error = PhaseStatus.RUNNING, utc_now(), None
        campaign.status, campaign.current_phase = CampaignStatus.IN_PROGRESS, phase
        try:
            setattr(campaign, phase.value, await self.runners[phase].run(campaign))
            phase_run.completed_at = utc_now()
            if phase == Phase.EXECUTION:
                phase_run.status, campaign.status = PhaseStatus.AWAITING_APPROVAL, CampaignStatus.AWAITING_APPROVAL
            else:
                phase_run.status = PhaseStatus.COMPLETED
                campaign.status = CampaignStatus.COMPLETED if phase == Phase.MONITORING else CampaignStatus.IN_PROGRESS
            campaign.updated_at = utc_now()
            return self.repository.save(campaign)
        except Exception as exc:
            phase_run.status, phase_run.error = PhaseStatus.FAILED, str(exc)
            campaign.status, campaign.updated_at = CampaignStatus.FAILED, utc_now()
            self.repository.save(campaign)
            raise

    async def run_until_blocked(self, campaign: CampaignState) -> CampaignState:
        while True:
            campaign = await self.run_phase(campaign, self._next_incomplete_phase(campaign))
            if campaign.status in {CampaignStatus.AWAITING_APPROVAL, CampaignStatus.COMPLETED}:
                return campaign

    def decide_execution(self, campaign: CampaignState, decision: ApprovalDecision,
                         actor: str, comment: str | None) -> CampaignState:
        execution_run = campaign.phase_runs[Phase.EXECUTION]
        if execution_run.status != PhaseStatus.AWAITING_APPROVAL:
            raise InvalidTransitionError("Execution is not awaiting approval")
        campaign.approvals.append(ApprovalRecord(
            phase=Phase.EXECUTION, decision=decision, actor=actor, comment=comment))
        if decision == ApprovalDecision.APPROVED:
            execution_run.status = PhaseStatus.COMPLETED
            campaign.current_phase, campaign.status = Phase.MONITORING, CampaignStatus.IN_PROGRESS
        else:
            execution_run.status, execution_run.error = PhaseStatus.FAILED, comment or "Execution rejected"
            campaign.status = CampaignStatus.FAILED
        campaign.updated_at = utc_now()
        return self.repository.save(campaign)

    @staticmethod
    def _next_incomplete_phase(campaign: CampaignState) -> Phase:
        for phase in PHASE_ORDER:
            phase_status = campaign.phase_runs[phase].status
            if phase_status == PhaseStatus.AWAITING_APPROVAL:
                raise InvalidTransitionError(f"{phase.value} is awaiting approval")
            if phase_status != PhaseStatus.COMPLETED:
                return phase
        raise InvalidTransitionError("Campaign is already complete")
