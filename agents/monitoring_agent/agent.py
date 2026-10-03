from google.adk.agents.llm_agent import Agent
from google.adk.agents.sequential_agent import SequentialAgent
from pydantic import BaseModel
from typing import Dict, List, Optional, Union


class MonitoringOutput(BaseModel):
    kpis: Dict[str, Optional[Union[float, int, str]]]
    analysis: List[str]
    recommendations: List[str]
    stakeholder_summary: str

kpi_reporter = Agent(
    model='gemini-2.5-flash',
    name='kpi_reporter',
    description='Monitoring Agent',
    instruction="Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. You are a Marketing Manager. Use campaign brief {campaign_brief}, planning output {planning_output}, and execution output {execution_output}. There is no connected analytics source. Include every success_metrics name from the brief exactly as a KPI key with null; all additional KPI values must also be null. Explain that measured performance is unavailable. Treat brief goals and metadata as planning inputs, not measured results.",
    output_key='kpi_report',
)

campaign_analyzer = Agent(
    model='gemini-2.5-flash',
    name='campaign_analyzer',
    description='Monitoring Agent',
    instruction="Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. Analyze campaign statistics using execution output {execution_output} and KPI report {kpi_report}. Clearly distinguish missing data from measured results.",
    output_key='campaign_analysis',
)   

tactic_and_strategy_adjuster = Agent(
    model='gemini-2.5-flash',
    name='tactic_and_strategy_adjuster',
    description='Monitoring Agent',
    instruction="Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. Given campaign brief {campaign_brief}, planning output {planning_output}, KPI report {kpi_report}, and campaign analysis {campaign_analysis}, recommend evidence-based actions to improve campaign effectiveness.",
    output_key='strategy_adjustments',
)

stakeholder_insight_reporter = Agent(
    model='gemini-2.5-flash',
    name='stakeholder_insight_reporter',
    description='Monitoring Agent',
    instruction="Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. Create a concise stakeholder report from campaign brief {campaign_brief}, {kpi_report}, {campaign_analysis}, and {strategy_adjustments}.",
    output_key='stakeholder_report',
)


monitoring_synthesizer = Agent(
    model='gemini-2.5-flash',
    name='monitoring_synthesizer',
    description='Produces the canonical structured monitoring phase output.',
    instruction="""Use the campaign brief {campaign_brief} as authoritative for industry, constraints, budget, and preferred channels. If industry is absent, use product and audience context without inventing an industry. Synthesize the monitoring phase using campaign brief
    {campaign_brief}, planning output {planning_output}, execution output
    {execution_output}, and:
    - KPI report: {kpi_report}
    - Campaign analysis: {campaign_analysis}
    - Strategy adjustments: {strategy_adjustments}
    - Stakeholder report: {stakeholder_report}

    There is no connected analytics source. Include every success_metrics name from
    the brief exactly as a KPI key with null, and use null for every additional
    KPI key. Explain that measured performance is unavailable. Never treat targets,
    metadata, or generated reports as measured results.
    Return only the structured output requested by the schema.
    """,
    output_schema=MonitoringOutput,
    output_key='monitoring',
)

root_agent = SequentialAgent(
    name='root_agent',
    description='Monitoring Agent',
    sub_agents=[kpi_reporter, campaign_analyzer, tactic_and_strategy_adjuster, stakeholder_insight_reporter, monitoring_synthesizer]
)
