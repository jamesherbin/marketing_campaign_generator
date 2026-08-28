from google.adk.agents.llm_agent import Agent
from google.adk.agents.sequential_agent import SequentialAgent
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class ScheduledActivity(BaseModel):
    channel: str
    action: str
    scheduled_for: Optional[datetime] = None
    status: str = 'prepared'


class ExecutionOutput(BaseModel):
    activities: List[ScheduledActivity]
    publication_summary: str
social_media_executor = Agent(
    model='gemini-2.5-flash',
    name='social_media_executor',
    description='Social Media Executor Agent',
    instruction='Use campaign brief {campaign_brief}, planning output {planning_output}, and development output {development_output}. Prepare the social assets for their declared channels. Do not publish. Clearly identify that human approval is required.',
    output_key='social_media_execution',
)

email_executor = Agent(
    model='gemini-2.5-flash',   
    name="email_executor",
    description="Email Executor Agent",
    instruction="Use campaign brief {campaign_brief}, development output {development_output}, and social preparation {social_media_execution}. Prepare marketing emails for review. Do not send them. Mark every email as requiring human approval.",
    output_key='email_execution',
)

channel_coordinator = Agent(
    model='gemini-2.5-flash',
    name='channel_coordinator',
    description='Channel Coordinator Agent',
    instruction="Coordinate the selected channels using planning output {planning_output}, development output {development_output}, social preparation {social_media_execution}, and email preparation {email_execution}. Do not submit advertising.",
    output_key='channel_coordination',
)

scheduler = Agent(
    model='gemini-2.5-flash',
    name='scheduler',
    description='Scheduler Agent',
    instruction="Generate a weekly schedule using campaign brief {campaign_brief} and coordinated activities {channel_coordination}.",
    output_key='schedule',
)


execution_synthesizer = Agent(
    model='gemini-2.5-flash',
    name='execution_synthesizer',
    description='Produces the canonical structured execution phase output.',
    instruction="""Create an execution preparation package from campaign brief
    {campaign_brief}, planning output {planning_output}, development output
    {development_output}, and:
    - Social preparation: {social_media_execution}
    - Email preparation: {email_execution}
    - Channel coordination: {channel_coordination}
    - Schedule: {schedule}

    Every activity must remain prepared, not published or sent. The publication
    summary must state that human approval and external integrations are required.
    Return only the structured output requested by the schema.
    """,
    output_schema=ExecutionOutput,
    output_key='execution',
)

root_agent = SequentialAgent(
    name='root_agent',
    description='Execution Agent',
    sub_agents = [social_media_executor, email_executor, channel_coordinator, scheduler, execution_synthesizer]
)
