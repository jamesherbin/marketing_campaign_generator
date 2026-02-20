from google.adk.agents.llm_agent import Agent

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Marketing Campaign Planning and Strategy Agent',
    instruction='You are a Chief Marketing Officer. Generate a Marketing Campaign and Plan the strategy execution for the user's Brand Input.  Complete research before generating the plan.  Only focus on planning tasks. You do not need to generate the assets that will display the Brand',
)
