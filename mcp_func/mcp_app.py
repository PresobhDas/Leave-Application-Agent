import logging, sys, inspect, requests
from utils.llm_utils import tool_properties, getAzureSecrets, WeatherData, EmployeeData, EmployeeLeaveData, RagData, generate_embeddings
from azure.cosmos.exceptions import CosmosResourceNotFoundError, CosmosHttpResponseError 
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient
import os
import json

log = logging.getLogger('mcp')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

INDEX_SEARCH_API_ENDPOINT = os.environ['AZURE_AI_SEARCH_API_ENDPOINT']
INDEX_SEARCH_API_KEY = os.environ['AZURE_AI_SEARCH_API_KEY']
INDEX_NAME = 'embedding-index'
COSMOS_URL = os.environ['COSMOS_DB_CONNECTION_STRING']

def register_tools(mcp_api_app):
    @mcp_api_app.mcp_tool_trigger(
        arg_name='context',
        tool_name='get_employee_master_record',
        description='Retrieve employee master information from Cosmos DB',
        tool_properties=tool_properties['get_employee_master_record']
    )
    def get_employee_master_record(context:str):
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        try:
            content = json.loads(context)
            log.info(f'Passed parameter for {inspect.currentframe().f_code.co_name} is {content}')
            employee_id = content['arguments']['employee_id']
            client = CosmosClient(
                url=COSMOS_URL,
                credential=DefaultAzureCredential()
            )

            db = client.get_database_client("leave-db")
            container = db.get_container_client("employee-master")
            resp = container.read_item(item=employee_id, partition_key=employee_id)
            emp_data = EmployeeData.model_validate(resp)
        except CosmosResourceNotFoundError:
            log.info(f'No records found for Employee : {employee_id}')
            return {'error':f'No records found for Employee : {employee_id}'}
        except CosmosHttpResponseError as err:
            log.error(f'Communication to Azure Cosmos failed with error {err}')
            return {'error':f'Communication to Azure Cosmos failed with error {err}'}
        except Exception as e:
            log.error(f'Failed with error {e}')

        return emp_data.model_dump_json()
    
    @mcp_api_app.mcp_tool_trigger(
        arg_name='context',
        tool_name='get_employee_leave_record',
        description='Retrieve employees leave information from Cosmos DB',
        tool_properties=tool_properties['get_employee_leave_record']
    )
    def get_employee_leave_record(context:str):
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        try: 
            content = json.loads(context)
            log.info(f'Passed parameter for {inspect.currentframe().f_code.co_name} is {content}')
            employee_id = content['arguments']['employee_id']
            client = CosmosClient(
                url=COSMOS_URL,
                credential=DefaultAzureCredential()
            )

            db = client.get_database_client("leave-db")
            container = db.get_container_client("employee-leaves")

            query = 'select * from c where c.employeeId = @employee_id'
            params = [{'name':'@employee_id', 'value':employee_id}]
            items = container.query_items(
                query=query,
                parameters=params,
                partition_key=employee_id
            )
            for item in items:
                emp_data = EmployeeLeaveData.model_validate(item)
        except CosmosResourceNotFoundError:
            log.info(f'No leave records found for Employee : {employee_id}')
            return {'error':f'No leave records found for Employee : {employee_id}'}
        except CosmosHttpResponseError as err:
            log.error(f'Communication to Azure Cosmos failed with error {err}')
            return {'error':f'Communication to Azure Cosmos failed with error {err}'}
        except Exception as e:
            log.error(f'Failed with error {e}')

        return emp_data.model_dump_json()

# @mcp_api_app.tool()
# async def get_leave_policy_document(inp_question:str):
#     embeddings = generate_embeddings(inp_question)
#     search_client = SearchClient(
#         endpoint=INDEX_SEARCH_API_ENDPOINT,
#         index_name=INDEX_NAME,
#         credential=AzureKeyCredential(INDEX_SEARCH_API_KEY)
#         )

#     vector_query = VectorizedQuery(
#         vector=embeddings,
#         k_nearest_neighbors=3,
#         fields="embedding"
#     )

#     results = search_client.search(
#         search_text=None,      # IMPORTANT for pure vector search
#         vector_queries=[vector_query]
#     )

#     for doc in results:
#         score = doc['@search.score']
#         doc_id = doc['id']
#         break

#     client = CosmosClient(
#         url=COSMOS_URL,
#         credential=DefaultAzureCredential()
#         )

#     db = client.get_database_client("policy-embeddings")
#     container = db.get_container_client("embedding-data")
#     try:
#         resp = container.read_item(item=doc_id, partition_key=doc_id)
#         rag_data = RagData.model_validate(resp)
#     except CosmosResourceNotFoundError:
#         log.info('No matching text found')
#         return {'No matching text found'}
#     except CosmosHttpResponseError as err:
#         log.error(f'Communication to Azure Cosmos failed with error {err}')
#         return {'error':f'Communication to Azure Cosmos failed with error {err}'}
    
#     rag_data.matchPercent = score
#     return rag_data.model_dump_json()

# @mcp_api_app.tool()
# async def get_weather(city:str):
#     log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

#     def get_lat_long(city:str):
#         log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
#         url = "https://geocoding-api.open-meteo.com/v1/search"
#         params = {
#             'name':city,
#             'count':1,
#             'language':'en',
#             'format':'json'
#         }

#         resp = requests.get(url=url, params=params)
#         data = resp.json()
#         if 'results' not in data:
#             log.info(f'CUSTOM LOG - {city} not a valid geographical location')
#             return None
        
#         result = data['results'][0]
#         return (result['latitude'], result['longitude'])
    
#     location = get_lat_long(city)
#     if location:
#         lat, long = location[0], location[1]
#         url = "https://api.open-meteo.com/v1/forecast"
#         params = {
#             'latitude':lat,
#             'longitude':long,
#             'current_weather':True
#         }

#         resp = requests.get(url=url, params=params).json()
#         log.info('get_weather API successfully called.')
#         current_weather = WeatherData(
#             latitude=resp['latitude'],
#             longitude=resp['longitude'],
#             temperature=resp['current_weather']['temperature'],
#             windspeed=resp['current_weather']['windspeed'],
#             winddirection=resp['current_weather']['winddirection']
#         )

#         return current_weather.model_dump_json()
#     return {'error':f'{city} is not a valid location'}
