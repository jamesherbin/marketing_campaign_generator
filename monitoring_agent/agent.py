from google.adk.agents.llm_agent import Agent

kpi_reporter = Agent(
    model='gemini-2.5-flash',
    name='kpi_reporter',
    description='Monitoring Agent',
    instruction=""
)

campaign_analyzer = Agent(
    model='gemini-2.5-flash',
    name='campaign_analyzer',
    description='Monitoring Agent',
    instruction=""
)   

tactic_and_strategy_adjuster = Agent(
    model='gemini-2.5-flash',
    name='tactic_and_strategy_adjuster',
    description='Monitoring Agent',
    instruction=""
)

stakeholder_insight_reporter = Agent(
    model='gemini-2.5-flash',
    name='stakeholder_insight_reporter',
    description='Monitoring Agent',
    instruction=""  
)

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Monitoring Agent',
    instruction='You are a Marketing Manager.  You are in the Consumer Packaged Goods Industry.  You are responsible for monitoring the results of a marketing campaign.  Generate a report using the sub agents',
    sub_agents=[kpi_reporter, campaign_analyzer, tactic_and_strategy_adjuster, stakeholder_insight_reporter]
)
