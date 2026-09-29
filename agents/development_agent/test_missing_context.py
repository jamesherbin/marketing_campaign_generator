"""Regression coverage for ADK subagents that require campaign context."""

import unittest

from google.adk.runners import InMemoryRunner
from google.genai import types

from development_agent.app.agent import channel_selection_and_media_planning


class MissingContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_channel_planner_fails_when_campaign_brief_is_not_in_session(self):
        """Starting this subagent alone must reproduce the missing-state error."""
        runner = InMemoryRunner(
            agent=channel_selection_and_media_planning,
            app_name="development_agent_missing_context_test",
        )
        session = await runner.session_service.create_session(
            app_name="development_agent_missing_context_test",
            user_id="test-user",
            state={},
        )

        with self.assertRaisesRegex(
            KeyError,
            r"Context variable not found: `campaign_brief` in agent 'channel_selection_and_media_planning'",
        ):
            async for _ in runner.run_async(
                user_id="test-user",
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Create a channel plan.")],
                ),
            ):
                pass


if __name__ == "__main__":
    unittest.main()
