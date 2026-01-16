from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from utils import get_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.tools import tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import logging

log = logging.getLogger("api")

api_server = FastAPI()
class InputDetails(BaseModel):
    inp_query:str

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.post('/agent')
async def call_agent(inp_details : Annotated[InputDetails, Body()]):
    chat_model = get_chat_model()
    try:
        async with streamable_http_client('https://leave-policy-agent-mcp-aseufdafbndad6a8.westus2-01.azurewebsites.net/mcp') as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                log.info('MCP session initialized')
                log.info(f'Data from MCP is {await session.call_tool(name='get_weather',arguments={'city':'Dallas'})}')
    except* Exception as e:
        log.exception(f'Failed with Exception: {e.exceptions}')

    return 'Ran Successful : OK'




