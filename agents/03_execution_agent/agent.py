from google.adk.agents.llm_agent import Agent
social_media_executor = Agent(
    model='gemini-2.5-flash',
    name='social_media_executor',
    description='Social Media Executor Agent',
    instruction='You are a Social Media Executive. You are in the Consumer Packaged Goods Industry. Submit the provided marketing assets to the declared social media channels.  Include human before submitting'
)

email_executor = Agent(
    model='gemini-2.5-flash',   
    name="email_executor",
    description="Email Executor Agent",
    instruction="You are responsible for generating and sending marketing emails.  You are in the Consumer Packaged Goods Industry.  Generate and send a marketing email.  Ask for permission after generation if the output is acceptable for send"
)

channel_coordinator = Agent(
    model='gemini-2.5-flash',
    name='channel_coordinator',
    description='Channel Coordinator Agent',
    instruction="You are a Social Media Marketing Manager.  Generate a list of channels that are most appropriate for a social media campaign.  Describe how to programatticaly submit advertising to these channels."
)

scheduler = Agent(
    model='gemini-2.5-flash',
    name='scheduler',
    description='Scheduler Agent',
    instruction="You are a Social Media Marketing Manager.  Generate a Weekly schedule for social media advertising."
)

root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Execution Agent',
    instruction='You are a Marketing Executive. You are in the Consumer Packaged Goods Industry.  You are responsible for submitting marketing assets to the selected channels.  Use MCP tools and subagents to accomplish these tasks',
    sub_agents = [social_media_executor, email_executor, channel_coordinator, scheduler]
)
