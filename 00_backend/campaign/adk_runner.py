from __future__ import annotations

import json
import re
from typing import Any, Generic, TypeVar

from google.adk.agents import BaseAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from .models import CampaignState, Phase


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
    ) -> None:
        if runner is None and agent is None:
            raise ValueError("agent is required when runner is not provided")
        self.app_name = app_name
        self.phase = phase
        self.output_model = output_model
        self.runner = runner or InMemoryRunner(agent=agent, app_name=app_name)

    async def run(self, campaign: CampaignState) -> OutputT:
        user_id = str(campaign.campaign_id)
        session_state = self._session_state(campaign)
        session = await self.runner.session_service.create_session(
            app_name=self.app_name,
            user_id=user_id,
            state=session_state,
        )
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
            if event.is_final_response():
                text = self._event_text(event)
                if text:
                    final_text = text

        if final_text is None:
            raise AdkRunnerError(f"{self.phase.value} agent returned no final text response")

        try:
            return self.output_model.model_validate_json(self._extract_json(final_text))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise AdkRunnerError(
                f"{self.phase.value} agent returned an invalid {self.output_model.__name__}: {exc}"
            ) from exc

    def _build_prompt(self, campaign: CampaignState) -> str:
        schema = json.dumps(self.output_model.model_json_schema(), separators=(",", ":"))
        state = campaign.model_dump_json(exclude_none=True)
        return (
            f"Run the {self.phase.value} phase for the campaign below. "
            "Return only one JSON object that conforms exactly to the supplied JSON Schema.\n"
            f"JSON Schema:\n{schema}\n"
            f"CampaignState:\n{state}"
        )

    @staticmethod
    def _session_state(campaign: CampaignState) -> dict[str, Any]:
        """Expose stable names that ADK instruction templates can reference."""
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
