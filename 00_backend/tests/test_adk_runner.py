import json
import unittest
from types import SimpleNamespace

from campaign.adk_runner import AdkRunnerAdapter, AdkRunnerError
from campaign.models import CampaignBrief, CampaignState, Phase, PhaseStatus, PlanningOutput, DevelopmentOutput


class FakeSessionService:
    def __init__(self) -> None:
        self.created_with = None

    async def create_session(self, **kwargs):
        self.created_with = kwargs
        return SimpleNamespace(id="session-1")


    async def delete_session(self, **kwargs):
        self.deleted_with = kwargs


class FakeEvent:
    def __init__(self, text: str | None, final: bool = True, author: str = "planning_synthesizer") -> None:
        parts = [] if text is None else [SimpleNamespace(text=text)]
        self.content = SimpleNamespace(parts=parts)
        self._final = final
        self.author = author

    def is_final_response(self) -> bool:
        return self._final


class FakeRunner:
    def __init__(self, events: list[FakeEvent]) -> None:
        self.session_service = FakeSessionService()
        self.events = events
        self.run_with = None

    async def run_async(self, **kwargs):
        self.run_with = kwargs
        for event in self.events:
            yield event


def state() -> CampaignState:
    return CampaignState(brief=CampaignBrief(
        brand="Acme",
        campaign_goal="Grow awareness",
        target_audience=["builders"],
        duration_weeks=4,
        budget=1_000,
    ))


def planning_payload() -> dict:
    return {
        "goals": ["Grow awareness"],
        "measurable_objectives": ["Reach 100 people"],
        "audience_segments": ["builders"],
        "positioning_statement": "Built for builders.",
        "value_proposition": "Build faster.",
        "key_messages": ["Build faster"],
        "recommended_channels": ["email"],
        "budget_by_channel": {"email": 1000},
    }


class AdkRunnerAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_validates_fenced_final_json_and_passes_campaign_state(self) -> None:
        response = f"```json\n{json.dumps(planning_payload())}\n```"
        runner = FakeRunner([
            FakeEvent("intermediate", final=False),
            FakeEvent(response),
        ])
        adapter = AdkRunnerAdapter(
            app_name="planning_agent",
            phase=Phase.PLANNING,
            output_model=PlanningOutput,
            runner=runner,
        )

        result = await adapter.run(state())

        self.assertEqual(result.recommended_channels, ["email"])
        session_state = runner.session_service.created_with["state"]
        self.assertIn("campaign_state", session_state)
        self.assertEqual(session_state["campaign_brief"]["brand"], "Acme")
        self.assertNotIn("planning_output", session_state)
        prompt = runner.run_with["new_message"].parts[0].text
        self.assertIn("JSON Schema", prompt)
        self.assertIn('"brand":"Acme"', prompt)

    async def test_exposes_completed_phase_outputs_as_named_state(self) -> None:
        campaign = state()
        campaign.planning = PlanningOutput.model_validate(planning_payload())
        campaign.phase_runs[Phase.PLANNING].status = PhaseStatus.COMPLETED
        runner = FakeRunner([FakeEvent(json.dumps(dict(creative_direction="Draft", assets=[], media_plan={})), author="development_synthesizer")])
        adapter = AdkRunnerAdapter(
            app_name="development_agent",
            phase=Phase.DEVELOPMENT,
            output_model=DevelopmentOutput,
            runner=runner,
        )

        await adapter.run(campaign)

        session_state = runner.session_service.created_with["state"]
        self.assertEqual(session_state["planning_output"]["recommended_channels"], ["email"])

    async def test_rejects_missing_final_response(self) -> None:
        adapter = AdkRunnerAdapter(
            app_name="planning_agent",
            phase=Phase.PLANNING,
            output_model=PlanningOutput,
            runner=FakeRunner([FakeEvent("draft", final=False)]),
        )
        with self.assertRaisesRegex(AdkRunnerError, "no final text"):
            await adapter.run(state())

    async def test_rejects_invalid_structured_output(self) -> None:
        adapter = AdkRunnerAdapter(
            app_name="planning_agent",
            phase=Phase.PLANNING,
            output_model=PlanningOutput,
            runner=FakeRunner([FakeEvent('{"goals": []}')]),
        )
        with self.assertRaisesRegex(AdkRunnerError, "invalid PlanningOutput"):
            await adapter.run(state())


if __name__ == "__main__":
    unittest.main()
