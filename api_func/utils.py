import os
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import logging, sys

log = logging.getLogger('utils')
log.setLevel(logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s"
)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

def get_chat_model() -> ChatOpenAI:
    log.info('Function Invoked')
    chat_model = ChatOpenAI(
        name='gpt-4o-mini',
        api_key=os.environ['OPENAI_API_KEY']
    )
    log.info('Retrieved the chat model')
    return chat_model

def get_mcp_session():
    log.info('Function Invoked')
    MCP_SERVER = 'https://leave-policy-agent-mcp-aseufdafbndad6a8.westus2-01.azurewebsites.net/mcp'
    try:
        with streamable_http_client(MCP_SERVER) as (read, write, session_id):
            with ClientSession(read, write) as MCP_SESSION:
                MCP_SESSION.initialize()
    except* Exception as e:
        log.exception(f'Failed with Exception: {e.exceptions}')

    log.info('Created MCP_SESSION')
    return MCP_SESSION

@tool
async def get_weather_tool(city: str, mcp_session):
    log.info('Function Invoked')
    '''
    Docstring for weather_tool
    :param city: Input city whose weather is being requested for.
    :type city: str

    This function tool get the city name as the input and returns the current weather information for that city
    '''
    resp = await mcp_session.call_tool(
                                        name = 'get_weather',
                                        arguments = {'city':city} 
                    )   

    return resp