from google.adk.agents.llm_agent import Agent

kpi_reporter = Agent(
    model='gemini-2.5-flash',
    name='kpi_reporter',
    description='Monitoring Agent',
    instruction="You are a Marketing Manager. You are in the Consumer Packaged Goods Industry. Generate a list of KPI to measure the effectiveness of a Social Media Marketing Campaign."
)

campaign_analyzer = Agent(
    model='gemini-2.5-flash',
    name='campaign_analyzer',
    description='Monitoring Agent',
    instruction="You are a Marketing Manager.  You are in the Consumer Packaged Goods Industry.  Generate a report to display statistics about the current marketing campaign."
)   

tactic_and_strategy_adjuster = Agent(
    model='gemini-2.5-flash',
    name='tactic_and_strategy_adjuster',
    description='Monitoring Agent',
    instruction="You are a Marketing Manager.  Given the results of the KPI and Campaign Analyzer reports, generate a set of actions to improve the effectiveness of the marketing campaign."
)

stakeholder_insight_reporter = Agent(
    model='gemini-2.5-flash',
    name='stakeholder_insight_reporter',
    description='Monitoring Agent',
    instruction="You are a Marketing Manager.  With the results from the KPI Report, Campaign Analyzer, and Tactic Strategy Adjuster,  Create a Report that can be shared with stakeholders."  
)

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Monitoring Agent',
    instruction='You are a Marketing Manager.  You are in the Consumer Packaged Goods Industry.  You are responsible for monitoring the results of a marketing campaign.  Generate a report using the sub agents',
    sub_agents=[kpi_reporter, campaign_analyzer, tactic_and_strategy_adjuster, stakeholder_insight_reporter]
)
