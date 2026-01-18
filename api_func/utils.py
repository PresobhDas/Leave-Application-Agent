import os
from langchain_openai import ChatOpenAI
from langchain.tools import tool
import logging, sys, inspect
from mcp import ClientSession

log = logging.getLogger('utils')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

def get_chat_model() -> ChatOpenAI:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    chat_model = ChatOpenAI(
        model= 'gpt-4o-mini',
        temperature=0.3,
        api_key=os.environ['OPENAI_API_KEY']
    )
    log.info('Retrieved the chat model')
    return chat_model

@tool
async def get_weather_tool(city: str, mcp_session:ClientSession):
    '''
    Docstring for weather_tool
    :param city: Input city whose weather is being requested for.
    :type city: str
    :param mcp_session: The MCP session that needs to be passed to call the tools from the MCP Server
    :type mcp_session: ClientSession

    This function tool get the city name as the input and returns the current weather information for that city
    '''
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    resp = await mcp_session.call_tool(
                                        name = 'get_weather',
                                        arguments = {'city':city} 
                    )   

    return resp