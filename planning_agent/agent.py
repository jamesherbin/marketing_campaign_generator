from google.adk.agents.llm_agent import Agent

goals_and_objectives = Agent(
    model='gemini-2.5-flash',
    name='goals_and_objectives',
    description='Marketing Campaign Goal and Objective Agent',
    instruction='You are a Marketing Director. Your industry is Consumer Packaged Goods.  Define the Goals and Objectives of a Marketing Campaign. Provide clear and quantifiable measurements that can be used to base other decisions.',
)

market_and_audience_research = Agent(
    model='gemini-2.5-flash',
    name='market_and_audience_research',
    description='Market Research and Market Audience Agent',
    instruction='You are a Market and Audience Researcher.  Your industry is Consumer Packaged Goods.  Generate an analysis of the Market and Consumer Audience.  Provide answers in clear manner that can be reused for decisions',
)

position_and_value_prop = Agent(
    model='gemini-2.5-flash',
    name='position_and_value_prop',
    description='Market Position and Product Value Proposition Agent',
    instruction='You are a Market Researcher.  Your industry is Consumer Packaged Goods.  Generate an analysis of the Market Position and Product Value Proposition.  Provide responses in format that can be used for further decisions.',
)

message_and_channels = Agent(
    model='gemini-2.5-flash',
    name='message_and_channels',
    description='Market Key Messages and Channels Agent',
    instruction='You are a CMO.  Your industry is Consumer Packaged Goods.  Generate the key product messages that will drive brand awareness and increase sales.  Generate results that can be used in a variety of marketing channels',
)

budget_manager = Agent(
    model='gemini-2.5-flash',
    name='budget_manager',
    description='Campaign Budget Manager',
    instruction='You are a CMO.  Your industry is Consumer Packaged Goods.  Generate a budget for a marketing plan. The budget should consider social media channels as well as print and tv.  Generate the budget so that it can be reused in other decisions.',
)

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Marketing Campaign Planning and Strategy Agent',
    instruction='You are a Chief Marketing Officer. Generate a Marketing Campaign and Plan the strategy execution for the Brand Input.  Complete research before generating the plan.  Only focus on planning tasks. You do not need to generate the assets that will display the Brand',
    sub_agents = [goals_and_objectives, market_and_audience_research, position_and_value_prop, message_and_channels, budget_manager]
)
