import os
from langchain_openai import ChatOpenAI
from langchain.tools import tool

def get_chat_model() -> ChatOpenAI:
    chat_model = ChatOpenAI(
        name='gpt-4o-mini',
        api_key=os.environ['OPENAI_API_KEY']
    )

    return chat_model

# @tool
# async def get_weather_tool(city: str):
#     '''
#     Docstring for weather_tool
#     :param city: Input city whose weather is being requested for.
#     :type city: str

#     This function tool get the city name as the input and returns the current weather information for that city
#     '''
#     resp = await MCP_SESSION.call_tool(
#                                         name = 'get_weather',
#                                         arguments = {'city':city} 
#                     )   

#     return resp