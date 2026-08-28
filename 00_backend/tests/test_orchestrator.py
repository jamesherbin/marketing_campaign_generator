import unittest

from campaign.models import (
    ApprovalDecision, CampaignBrief, CampaignState, CampaignStatus, Phase, PhaseStatus,
)
from campaign.orchestrator import CampaignOrchestrator, InvalidTransitionError
from campaign.repository import InMemoryCampaignRepository


def campaign_state() -> CampaignState:
    return CampaignState(brief=CampaignBrief(
        brand="Acme",
        campaign_goal="Increase brand awareness",
        target_audience=["small business owners"],
        duration_weeks=8,
        budget=25_000,
        preferred_channels=["social_media", "email", "digital_ads"],
        success_metrics=["reach", "engagement_rate"],
    ))


class CampaignOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repository = InMemoryCampaignRepository()
        self.orchestrator = CampaignOrchestrator(self.repository)
        self.campaign = self.repository.create(campaign_state())

    async def test_full_lifecycle_stops_for_approval_then_completes(self) -> None:
        waiting = await self.orchestrator.run_until_blocked(self.campaign)
        self.assertEqual(waiting.status, CampaignStatus.AWAITING_APPROVAL)
        self.assertEqual(waiting.phase_runs[Phase.EXECUTION].status, PhaseStatus.AWAITING_APPROVAL)
        self.assertIsNotNone(waiting.planning)
        self.assertIsNotNone(waiting.development)
        self.assertIsNotNone(waiting.execution)
        self.assertAlmostEqual(sum(waiting.planning.budget_by_channel.values()), 25_000)

        approved = self.orchestrator.decide_execution(
            waiting, ApprovalDecision.APPROVED, "reviewer@example.com", "Ready")
        complete = await self.orchestrator.run_until_blocked(approved)
        self.assertEqual(complete.status, CampaignStatus.COMPLETED)
        self.assertIsNotNone(complete.monitoring)
        self.assertEqual(len(complete.approvals), 1)

    async def test_phase_order_is_enforced(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            await self.orchestrator.run_phase(self.campaign, Phase.DEVELOPMENT)

    async def test_rejection_fails_execution(self) -> None:
        waiting = await self.orchestrator.run_until_blocked(self.campaign)
        rejected = self.orchestrator.decide_execution(
            waiting, ApprovalDecision.REJECTED, "reviewer@example.com", "Revise claims")
        self.assertEqual(rejected.status, CampaignStatus.FAILED)
        self.assertEqual(rejected.phase_runs[Phase.EXECUTION].error, "Revise claims")


if __name__ == "__main__":
    unittest.main()
