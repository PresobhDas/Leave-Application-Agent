# import requests
from fastapi import FastAPI
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
import os

api_server = FastAPI()
class InputDetails(BaseModel):
    inp_query:str

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.get('/agent')
async def call_agent(inp_details : InputDetails):
    chat_model = ChatOpenAI(
        name='gpt-4o-mini',
        api_key=os.environ['OPENAI_API_KEY']
    )
    inp_query = inp_details.inp_query

    response = chat_model.invoke(inp_query)

    return response


