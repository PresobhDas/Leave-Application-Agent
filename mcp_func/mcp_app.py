import logging, sys, inspect, requests
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from utils.llm_utils import WeatherData, EmployeeData

log = logging.getLogger('mcp')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

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

@mcp_api_app.prompt()
async def get_input_prompt_human(question:str, context:str):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    human_message=f"""This is the question : {question}."""

    return human_message  

@mcp_api_app.prompt()
async def get_input_prompt_system():
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    system_message = '''
    You are a helpful AI bot that does the following.
    1. Understand the question given to you by the user.
    2. Take the following actions ONLY with priority in the given order:
        a) If the question is regular conversaion, respond naturally and conversationally as no information retrieval is needed.
        b) Try to answer based on your internal knowledge.
        c) Call external tools provided to you. Details of the different tools ar as follows. There is NO particular order in which the below tools need to be invoked. Directly call the right tool as needed. No need to follow the below precedence.
            1) Tool Name : load_RAG_context_tool.
                Description: RAG tool to see if the question has potential answers from RAG output. If the RAG output has the necessary information, then provide the citation as well. For eg: PageNo from the given context.
            2) Tool Name: weather_tool
                Description: weather_tool to retrieve the weather information for any given location. 
            3) Tool Name: load_data_from_db
                Description: load_data_from_db to load Customer information from the Postgres SQL Database. If the question involves querying data from the Database based on the CUSTOMER ID, call this tool to pass the CUSTOMER ID as a parameter to read and pass back the information read from the databse to the LLM
        d) If NONE of the THE ABOVE works, say 'I Don't know the answer'.      
    '''

    return system_message

@mcp_api_app.tool()
async def get_employee_record(employee_id:str):
    from azure.identity import DefaultAzureCredential
    from azure.cosmos import CosmosClient
    import os

    COSMOS_URL = os.environ['COSMOS_DB_CONNECTION_STRING']

    client = CosmosClient(
        url=COSMOS_URL,
        credential=DefaultAzureCredential()
    )

    db = client.get_database_client("leave-db")
    container = db.get_container_client("employee-master")

    resp = container.read_item(item=employee_id, partition_key=employee_id)
    emp_data = EmployeeData.model_validate(resp)
    return emp_data.model_dump_json()

@mcp_api_app.tool()
async def get_weather(city:str):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

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

        resp = requests.get(url=url, params=params).json()
        log.info('get_weather API successfully called.')
        current_weather = WeatherData(
            latitude=resp['latitude'],
            longitude=resp['longitude'],
            temperature=resp['current_weather']['temperature'],
            windspeed=resp['current_weather']['windspeed'],
            winddirection=resp['current_weather']['winddirection']
        )

        return current_weather.model_dump_json()
    
mcp_server = mcp_api_app.streamable_http_app()