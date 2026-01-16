from mcp.server.fastmcp import FastMCP
import requests
from mcp.server.transport_security import TransportSecuritySettings
import logging

log = logging.getLogger("api")
log.setLevel(logging.INFO)
logging.getLogger().setLevel(logging.INFO) 
log.info('MCP Module loaded')

HOST = 'leave-policy-agent-mcp-aseufdafbndad6a8.westus2-01.azurewebsites.net'

mcp_api_app = FastMCP(
    transport_security=TransportSecuritySettings(
        # allow just your app host (tightest)
        allowed_hosts=[
                HOST,
                f'{HOST}:443' # optional wildcard
        ],
    )
)

@mcp_api_app.tool()
async def get_weather(city:str):
    log.info('Successfully got into the MCP for get_weather')
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
        log.info('get_weather API successfully called.')
        return resp.json()
    
mcp_server = mcp_api_app.streamable_http_app()