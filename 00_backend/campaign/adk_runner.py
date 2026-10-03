from __future__ import annotations

import asyncio
import logging
import json
import re
from typing import Any, Generic, TypeVar

from google.adk.agents import BaseAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from .models import PHASE_ORDER, CampaignState, Phase, PhaseStatus, DevelopmentOutput, ExecutionOutput, MonitoringOutput


logger = logging.getLogger(__name__)


OutputT = TypeVar("OutputT", bound=BaseModel)


class AdkRunnerError(RuntimeError):
    """Raised when an ADK invocation cannot produce a valid phase result."""


class AdkRunnerAdapter(Generic[OutputT]):
    """Runs an ADK root agent and validates its final response as a phase model."""

    def __init__(
        self,
        *,
        app_name: str,
        phase: Phase,
        output_model: type[OutputT],
        agent: BaseAgent | None = None,
        runner: Any | None = None,
        synthesizer_name: str | None = None,
    ) -> None:
        if runner is None and agent is None:
            raise ValueError("agent is required when runner is not provided")
        self.app_name = app_name
        self.phase = phase
        self.output_model = output_model
        self.synthesizer_name = synthesizer_name or f"{phase.value}_synthesizer"
        self.runner = runner or InMemoryRunner(agent=agent, app_name=app_name)

    async def run(self, campaign: CampaignState) -> OutputT:
        user_id = str(campaign.campaign_id)
        session_state = self._session_state(campaign)
        session = await self.runner.session_service.create_session(
            app_name=self.app_name,
            user_id=user_id,
            state=session_state,
        )
        try:
            message = types.Content(
                role="user",
                parts=[types.Part.from_text(text=self._build_prompt(campaign))],
            )

            final_text: str | None = None
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=message,
            ):
                if (
                    getattr(event, "author", None) == self.synthesizer_name
                    and not getattr(event, "partial", False)
                    and event.is_final_response()
                ):
                    final_text = self._event_text(event)

            if not final_text:
                raise AdkRunnerError(f"{self.phase.value} agent returned no final text response")

            try:
                output = self.output_model.model_validate_json(self._extract_json(final_text))
            except (ValidationError, ValueError, json.JSONDecodeError):
                raise AdkRunnerError(
                    f"{self.phase.value} agent returned an invalid {self.output_model.__name__}"
                ) from None
            self._validate_generated_output(output, campaign)
            return output
        finally:
            await self._delete_session(user_id, session.id)

    def _validate_generated_output(self, output: BaseModel, campaign: CampaignState) -> None:
        """Generation-only rules; historical records keep their existing schema."""
        if isinstance(output, DevelopmentOutput):
            if any(asset.status != "draft" for asset in output.assets):
                raise AdkRunnerError("development assets must remain draft")
        elif isinstance(output, ExecutionOutput):
            if any(activity.status != "prepared" for activity in output.activities):
                raise AdkRunnerError("execution activities must remain prepared")
        elif isinstance(output, MonitoringOutput):
            # No trusted analytics connector exists. Metadata/model claims are not evidence.
            if not set(campaign.brief.success_metrics).issubset(output.kpis):
                raise AdkRunnerError("monitoring output is missing requested metrics")
            if any(value is not None for value in output.kpis.values()):
                raise AdkRunnerError("monitoring metrics must be null without analytics")

    async def _delete_session(self, user_id: str, session_id: str) -> None:
        async def delete() -> None:
            try:
                await self.runner.session_service.delete_session(
                    app_name=self.app_name, user_id=user_id, session_id=session_id,
                )
            except Exception:
                # Never log exception text, session identifiers, or campaign content.
                logger.warning("ADK session cleanup failed for phase %s", self.phase.value)

        cleanup = asyncio.create_task(delete())
        cancelled = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled = True
        # Retrieve any task exception; ordinary deletion errors are handled above.
        cleanup.result()
        if cancelled:
            raise asyncio.CancelledError()

    def _build_prompt(self, campaign: CampaignState) -> str:
        schema = json.dumps(self.output_model.model_json_schema(), separators=(",", ":"))
        state = self._phase_context(campaign).model_dump_json(exclude_none=True)
        return (
            f"Run the {self.phase.value} phase for the campaign below. "
            "Return only one JSON object that conforms exactly to the supplied JSON Schema.\n"
            f"JSON Schema:\n{schema}\n"
            f"CampaignState:\n{state}"
        )

    def _phase_context(self, campaign: CampaignState) -> CampaignState:
        """Remove unusable results from a private copy, including retry leftovers."""
        context = campaign.model_copy(deep=True)
        upstream = PHASE_ORDER[:PHASE_ORDER.index(self.phase)]
        for phase in PHASE_ORDER:
            if phase not in upstream or context.phase_runs[phase].status != PhaseStatus.COMPLETED:
                setattr(context, phase.value, None)
        return context

    def _session_state(self, campaign: CampaignState) -> dict[str, Any]:
        """Expose stable names that ADK instruction templates can reference."""
        campaign = self._phase_context(campaign)
        values: dict[str, Any] = {
            "campaign_state": campaign.model_dump(mode="json"),
            "campaign_brief": campaign.brief.model_dump(mode="json"),
        }
        for phase in Phase:
            output = getattr(campaign, phase.value)
            if output is not None:
                values[f"{phase.value}_output"] = output.model_dump(mode="json")
        return values

    @staticmethod
    def _event_text(event: Any) -> str:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        return "".join(part.text for part in parts if getattr(part, "text", None)).strip()

    @staticmethod
    def _extract_json(text: str) -> str:
        fenced = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, re.DOTALL | re.IGNORECASE)
        return fenced.group(1) if fenced else text.strip()
