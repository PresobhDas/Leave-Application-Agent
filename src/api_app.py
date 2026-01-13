# import requests
from fastapi import FastAPI

api_server = FastAPI()

@api_server.get("ping")
async def ping():
    return {"message": "pong"}

@api_server.get('get_weather')
async def get_weather():
    return {'city': 'Dallas'}

