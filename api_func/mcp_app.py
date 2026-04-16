from mcp.server.fastmcp import FastMCP
import logging, sys, inspect, requests, os
from utils.model_contracts import WeatherDataResponse, WeatherData, RagData, RagDataResponseModel, EmployeeMasterResponseModel, EmployeeMaster
from utils.llm_utils import get_azure_openai_client, azure_ai_search_endpoint
from azure.search.documents import SearchClient
from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient

log = logging.getLogger('mcp')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

def register_tools(mcp_server:FastMCP):
    @mcp_server.tool()
    async def get_weather(city:str):
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
            log.info(f'CUSTOM LOG - Calling external API : {url}')
            resp = requests.get(url=url, params=params, timeout=30)
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
            log.info(f'CUSTOM LOG - Calling external API : {url}')
            resp = requests.get(url=url, params=params, timeout=60).json()
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
    
    @mcp_server.tool()
    async def get_rag_document(inp_question: str):
        log.info(f'CUSTOM LOG - Entered MCP tool: {inspect.currentframe().f_code.co_name} with parameter {inp_question}')
        rag_response = RagDataResponseModel()
        try:
            openai_client = get_azure_openai_client()
            query_embeddings = openai_client.embeddings.create(
                model='text-embedding-3-small',
                input=inp_question
            )
            index_name='leave_agent_vector_index'
            azure_ai_search_client = SearchClient(
                        endpoint=azure_ai_search_endpoint,
                        index_name=index_name,
                        credential= DefaultAzureCredential()
                        )
            result = azure_ai_search_client.search(
                search_text = None,
                vector_queries=[
                    {
                        'kind' : 'vector',
                        'vector' : query_embeddings.data[0].embedding,
                        'fields' : 'embedding',
                        'k' : 5
                    }
                ],
                query_type = 'semantic',
                semantic_configuration_name= 'default',
                top=2,
                select=['id', 'content_text', 'metadata_title']
            )
            result_list = list(result)
            for result in result_list:
                rag_response.dataFound = 'FOUND'
                rag_response.results.append(
                    RagData(
                        score = result['@search.score'],
                        text = result['content_text'],
                        title = result['metadata_title']
                    )
                )
        except Exception as err:
            log.info(f'CUSTOM LOG - Error in MCP tool {inspect.currentframe().f_code.co_name} with error {err}')

        return rag_response.model_dump_json()
    
    @mcp_server.tool
    async def get_employee_master_record(employee_id : str):
        log.info(f'CUSTOM LOG - Entered MCP tool: {inspect.currentframe().f_code.co_name} with parameter {employee_id}')
        employee_master = EmployeeMasterResponseModel()
        try:
            table_service = TableServiceClient(
                endpoint=os.environ.get('TABLE_ACCOUNT_URL'),
                credential=DefaultAzureCredential()
            )

            table_client = table_service.get_table_client('EmployeeMaster')
            entities = table_client.query_entities(
                query_filter=f'RowKey eq {employee_id}'
            )

            for entity in entities:
                employee_master.dataFound = 'FOUND'
                employee_master.employee.append(
                    EmployeeMaster(
                        employeeId=entity['RowKey'],
                        name=entity['Name'],
                        department=entity['PartitionKey'],
                        location=entity['Location'],
                        DOB=entity['DOB'],
                        isActive=entity['Active']
                    )
                )
        except Exception as err:
            log.info(f'CUSTOM LOG - Error in MCP tool {inspect.currentframe().f_code.co_name} with error {err}')
        
        return employee_master.model_dump_json()

