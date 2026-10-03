from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.llm_agent import Agent
from pydantic import BaseModel, Field
from typing import Dict, List

class GoalsAndObjectives(BaseModel):
    goals: list[str] = Field(description="List of marketing campaign goals")
    objectives: list[str] = Field(description="List of quantifiable objectives")

goals_and_objectives = Agent(
    model='gemini-2.5-flash',
    name='goals_and_objectives',
    description='Marketing Campaign Goal and Objective Agent',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a Marketing Director.


    Campaign brief: {campaign_brief}

    Task:
    - Define the Goals and Objectives of a Marketing Campaign.
    - Provide clear and quantifiable measurements that can be used to base other decisions.
    """,
    output_schema=GoalsAndObjectives,
    output_key='goals_and_objectives'
)

class MarketAndAudienceResearch(BaseModel):
    markets: List[str] = Field(description="Regional Markets that this product should be advertised.")
    audiences: list[str] = Field(description="List of audiences that should see this product's advertising")

market_and_audience_research = Agent(
    model='gemini-2.5-flash',
    name='market_and_audience_research',
    description='Market Research and Market Audience Agent',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a Market and Audience Researcher.

    Campaign brief: {campaign_brief}
    Goals and objectives already defined: {goals_and_objectives}

    Task:
    - Generate an analysis of the Market and Consumer Audience.
    - Provide answers in clear manner that can be reused for decisions
    """,
    output_schema=MarketAndAudienceResearch,
    output_key='market_and_audience_research'
)


class PositionAndValueProposition(BaseModel):
    positioning_statement: str = Field(description="A product positioning statement")
    value_proposition: str = Field(description="Value Proposition statements")


position_and_value_prop = Agent(
    model='gemini-2.5-flash',
    name='position_and_value_prop',
    description='Market Position and Product Value Proposition Agent',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a Market Researcher.

    Campaign brief: {campaign_brief}
    Goals and objectives: {goals_and_objectives}
    Market and audience research: {market_and_audience_research}

    Task:
    - Generate an analysis of the Market Position and Product Value Proposition.
    - Provide responses in format that can be used for further decisions.
    """,
    output_schema=PositionAndValueProposition,
    output_key='position_and_value_prop'
)

class MessageAndChannels(BaseModel):
    messages: List[str] = Field(description="List of Product Messages to be applied to marketing copy")
    channels: List[str] = Field(description="List of Channels to place the messages")

message_and_channels = Agent(
    model='gemini-2.5-flash',
    name='message_and_channels',
    description='Market Key Messages and Channels Agent',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a CMO.

    Campaign brief: {campaign_brief}
    Audience research: {market_and_audience_research}
    Positioning and value proposition: {position_and_value_prop}

    Task:
    - Generate the key product messages that will drive brand awareness and increase sales.
    - Generate results that can be used in a variety of marketing channels
    """,
    output_schema=MessageAndChannels,
    output_key='message_and_channels'
)

class BudgetManager(BaseModel):
    q1: float = Field(description="q1 budget amount")
    q2: float = Field(description="q2 budget amount")
    q3: float = Field(description="q3 budget amount")
    q4: float = Field(description="q4 budget amount")

budget_manager = Agent(
    model='gemini-2.5-flash',
    name='budget_manager',
    description='Campaign Budget Manager',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a CMO.

    Campaign brief: {campaign_brief}
    Recommended messages and channels: {message_and_channels}

    Task:
    - Generate a budget for a marketing plan.
    - Use the brief's preferred channels and constraints; do not add incompatible channels.
    - Generate the budget so that it can be reused in other decisions.
    """,
    output_schema=BudgetManager,
    output_key='budget_manager'
)


class PlanningOutput(BaseModel):
    goals: List[str]
    measurable_objectives: List[str]
    audience_segments: List[str]
    positioning_statement: str
    value_proposition: str
    key_messages: List[str]
    recommended_channels: List[str]
    budget_by_channel: Dict[str, float]


planning_synthesizer = Agent(
    model='gemini-2.5-flash',
    name='planning_synthesizer',
    description='Produces the canonical structured planning phase output.',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. Synthesize the completed planning research into one campaign plan.

    Campaign brief: {campaign_brief}
    Use these session results:
    - Goals and objectives: {goals_and_objectives}
    - Market and audience research: {market_and_audience_research}
    - Positioning and value proposition: {position_and_value_prop}
    - Messages and channels: {message_and_channels}
    - Budget: {budget_manager}

    Preserve the campaign brief's total budget. Allocate it by channel in
    budget_by_channel. Return only the structured output requested by the schema.
    """,
    output_schema=PlanningOutput,
    output_key='planning',
)

root_agent = SequentialAgent(
    name='root_agent',
    description='Marketing Campaign Planning and Strategy Agent',
    sub_agents = [goals_and_objectives, market_and_audience_research, position_and_value_prop, message_and_channels, budget_manager, planning_synthesizer]
)
