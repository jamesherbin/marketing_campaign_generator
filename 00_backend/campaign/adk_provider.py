"""Per-application provider configuration for the locked ADK Gemini adapter."""
from functools import cached_property

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.models.google_llm import Gemini
from google.genai import Client, types
from pydantic import PrivateAttr

from .config import Settings


class ConfiguredGemini(Gemini):
    # Keep credentials out of model dumps, agent representations and schemas.
    _settings: Settings = PrivateAttr()

    def __init__(self, *, model: str, settings: Settings):
        super().__init__(model=model)
        self._settings = settings.model_copy(deep=True)

    @cached_property
    def api_client(self) -> Client:
        # Lazy construction preserves credential-free startup/import checks.
        settings = self._settings
        kwargs = {}
        if settings.google_genai_use_vertexai:
            kwargs = dict(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )
        elif key := settings.google_api_key or settings.gemini_api_key:
            kwargs = dict(vertexai=False, api_key=key.get_secret_value())
        # No explicit auth settings: retain the SDK's ambient discovery path.
        return Client(
            **kwargs,
            http_options=types.HttpOptions(
                headers=self._tracking_headers(),
                retry_options=self.retry_options,
                base_url=self.base_url,
            ),
        )


def configured_agent(agent: BaseAgent, settings: Settings) -> BaseAgent:
    """Clone the agent tree so separate apps never mutate shared package exports."""
    clone = agent.clone()

    def configure(node: BaseAgent) -> None:
        if isinstance(node, LlmAgent) and isinstance(node.model, str):
            node.model = ConfiguredGemini(model=node.model, settings=settings)
        for child in node.sub_agents:
            configure(child)

    configure(clone)
    return clone
