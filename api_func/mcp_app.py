from mcp.server.fastmcp import FastMCP
import logging, sys, inspect, requests
from utils.model_contracts import WeatherDataResponse, WeatherData

log = logging.getLogger('mcp')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

def register_tools(mcp_server:FastMCP):
    @mcp_server.tool()
    async def get_weather_tool(city:str):
        log.info(f'CUSTOM LOG - Entered MCP tool: {inspect.currentframe().f_code.co_name}')
        '''
        Docstring for get_weather_tool
        :param city: Input city whose weather is being requested for.
        :type city: str

        This function tool get the city name as the input and returns the current weather information for that city
        '''
        def get_lat_long(city:str):
            log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
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
                log.info(f'CUSTOM LOG - {city} not a valid geographical location')
                return None
            
            result = data['results'][0]
            return (result['latitude'], result['longitude'])
        
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        weather_response = WeatherDataResponse()
        log.info(f'Passed parameter for {inspect.currentframe().f_code.co_name} is {city}')
        location = get_lat_long(city)
        if location:
            lat, long = location[0], location[1]
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                'latitude':lat,
                'longitude':long,
                'current_weather':True
            }

            resp = requests.get(url=url, params=params).json()
            log.info('get_weather API successfully called.')
            current_weather = WeatherData(
                latitude=resp['latitude'],
                longitude=resp['longitude'],
                temperature=resp['current_weather']['temperature'],
                windspeed=resp['current_weather']['windspeed'],
                winddirection=resp['current_weather']['winddirection']
            )
            weather_response.dataFound = 'FOUND'
            weather_response.weatherData = current_weather

        return weather_response.model_dump_json()