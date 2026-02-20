from google.adk.agents.llm_agent import Agent

#CONTENT DESIGN AND CREATION
content_design_and_creation = Agent(
    model='gemini-2.5-flash',
    name='content_design_and_creation',
    description='Content Design and Creation Agent',
    instruction='You are a Content Designer. You are responsible for generating images and videos that adher to brand standards.  Create a marketing image that conforms to brand guidelines',
)

#Message and Value Proposition
message_and_value_prop = Agent(
    model='gemini-2.5-flash',
    name='message_and_value_prop',
    description='Message and Value Proposition Agent',
    instruction='You are a Marketing Expert.  You are in the Consumer Packaged Goods industry.  Generate Product Messaging and Value Proposition text copy that adheres to brand guidelines',
)

#CHANNEL SELECTION AND MEDIA PLANNING
channel_selection_and_media_planning = Agent(
    model='gemini-2.5-flash',
    name='channel_selection_and_media_planning',
    description='Channel Selection and Media Planning Agent',
    instruction='You are a Marketing Channel Expert.  You are in the Consumer Packaged Goods Industry.  Generate a list of channels that are appropriate and the best way to reach them.',
)

#DEVELOPMENT AGENT _ ROOT AGENT
root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='Content Development Agent',
    instruction='You are the Content Creation Director.  You are in the Consumer Packaged Goods Industry.  Generate a set of Content according to the results of the subagents.',
    sub_agents = [content_design_and_creation, message_and_value_prop, channel_selection_and_media_planning]
)
