# import requests
from fastapi import FastAPI
from pydantic import BaseModel
from langgraph.graph import START, END, StateGraph
from utils import get_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

api_server = FastAPI()
class InputDetails(BaseModel):
    inp_query:str

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.get('/agent')
async def call_agent(inp_details : InputDetails) -> AIMessage:
    chat_model = get_chat_model()

    inp_query = inp_details.inp_query
    response = chat_model.invoke(inp_query)

    return response


