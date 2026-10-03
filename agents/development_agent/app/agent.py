from google.adk.agents.llm_agent import Agent
from google.adk.agents.sequential_agent import SequentialAgent
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


class ContentAsset(BaseModel):
    asset_id: UUID = Field(default_factory=uuid4)
    channel: str
    format: str
    headline: str
    body: str
    call_to_action: Optional[str] = None
    status: str = 'draft'


class DevelopmentOutput(BaseModel):
    creative_direction: str
    assets: List[ContentAsset]
    media_plan: Dict[str, Any]

#CHANNEL SELECTION AND MEDIA PLANNING
channel_selection_and_media_planning = Agent(
    model='gemini-2.5-flash',
    name='channel_selection_and_media_planning',
    description='Channel Selection and Media Planning Agent',
    instruction='Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a Marketing Channel Expert. Use campaign brief {campaign_brief} and completed planning output {planning_output}. Generate the channel and media approach without changing the completed strategy.',
    output_key='channel_selection_and_media_planning',
)

#Message and Value Proposition
message_and_value_prop = Agent(
    model='gemini-2.5-flash',
    name='message_and_value_prop',
    description='Message and Value Proposition Agent',
    instruction='Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a Marketing Expert. Use campaign brief {campaign_brief}, planning output {planning_output}, and channel plan {channel_selection_and_media_planning}. Generate channel-ready messaging that preserves the planned value proposition.',
    output_key='message_and_value_prop',
)

#CONTENT DESIGN AND CREATION
content_design_and_creation = Agent(
    model='gemini-2.5-flash',
    name='content_design_and_creation',
    description='Content Design and Creation Agent',
    instruction='Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a Content Designer. Use campaign brief {campaign_brief}, planning output {planning_output}, channel plan {channel_selection_and_media_planning}, and messaging {message_and_value_prop}. Create draft text assets that conform to those decisions. Describe visual concepts in words only. Do not generate binary images or claim image files were generated or stored.',
    output_key='content_design_and_creation',
)


development_synthesizer = Agent(
    model='gemini-2.5-flash',
    name='development_synthesizer',
    description='Produces the canonical structured development phase output.',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. Create the final development package from campaign brief
    {campaign_brief} and completed planning output {planning_output}, plus:
    - Channel/media plan: {channel_selection_and_media_planning}
    - Messaging: {message_and_value_prop}
    - Creative result: {content_design_and_creation}

    Produce at least one draft text ContentAsset per recommended channel, with status draft. Describe visual concepts in words only; do not claim image files were generated or stored. Never claim
    an asset was published. Return only the structured output requested by the schema.
    """,
    output_schema=DevelopmentOutput,
    output_key='development',
)

#DEVELOPMENT AGENT _ ROOT AGENT
root_agent = SequentialAgent(
    #model='gemini-2.5-flash',
    name='root_agent',
    description='Content Development Agent',
    sub_agents = [channel_selection_and_media_planning, message_and_value_prop, content_design_and_creation, development_synthesizer]
)
