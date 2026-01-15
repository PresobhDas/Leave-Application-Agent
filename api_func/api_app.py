from fastapi import FastAPI
from pydantic import BaseModel
from langgraph.graph import START, END, StateGraph
from utils import get_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.tools import tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

api_server = FastAPI()
class InputDetails(BaseModel):
    inp_query:str

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.get('/agent')
async def call_agent(inp_details : InputDetails) -> AIMessage:
    chat_model = get_chat_model()

    async with streamable_http_client('https://leave-policy-agent-mcp-aseufdafbndad6a8.westus2-01.azurewebsites.net/mcp') as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                name='get_weather',
                arguments={'city':'Dallas'}
            )

    return result




