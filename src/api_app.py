import requests
from fastapi import FastAPI

api_server = FastAPI()

@api_server.get('/get_weather')
async def get_weather(city='Dallas'):

    def get_lat_long(city:str):
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            'name':city,
            'count':1,
            'language':'en',
            'format':'json'
        }

        resp = requests.get(url=url, params=params)
        data = resp.json()
        if 'results' not in data:
            raise ValueError(f'City:{city} not found')
        
        result = data['results'][0]
        return result['latitude'], result['longitude']
    
    lat, long = get_lat_long(city)
    if lat and long:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude':lat,
            'longitude':long,
            'current_weather':True
        }

        resp = requests.get(url=url, params=params)
        return resp.json()
