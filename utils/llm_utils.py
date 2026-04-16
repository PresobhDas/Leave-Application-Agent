import os, logging, sys, inspect, re, json
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import MessagesState
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from utils.model_contracts import EmployeeMasterResponseModel, EmployeeLeaveResponseModel, WeatherDataResponse, RagDataResponseModel
from mcp.server.fastmcp import FastMCP
from typing import List, Dict
from langchain_core.documents import Document
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex
from openai import AzureOpenAI
from pathlib import Path

VAULT_URL = os.environ.get('VAULT_URL')

log = logging.getLogger('utils')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

azure_ai_search_endpoint = os.environ.get('AZURE_AI_SEARCH_CONNECTION_STRING')
class RagState(MessagesState):
    question:str
    tool_execution_count: int

def get_prompts(prompt_name:str, question:str|None=None):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    prompt_dict = dict()

    prompt_dict['input_prompt_human'] = f"""This is the question : {question}."""
    prompt_dict['input_prompt_system'] = '''
    You are a helpful AI bot that does the following.
    1. Understand the question given to you by the user.
    2. Take the following actions ONLY with priority in the given order:
        a) Call external tools provided to you. Details of the different tools ar as follows. There is NO particular order in which the below tools need to be invoked. Directly call the right tool as needed. No need to follow the below precedence. If tools returns 'NOT FOUND', quit retrying and exit with the proper response of not getting data from that particular tool.
            1) Tool Name : get_employee_master_record.
                Description: Retrieve the employee master information from the Azure Cosmos DB. This queries the NO SQL database based on the given Employee ID.
            2) Tool Name : get_employee_leave_record.
                Description: Retrieve the employee leave information from the Azure Cosmos DB. This queries the NO SQL database based on the given Employee ID.
            3) Tool Name : get_rag_document_tool.
                Description: This is the RAG retrieval tool and queries the Azure AI Search using the vector embeddings of the given input text based on similarity.
            4) Tool Name: get_weather_tool
                Description: get_weather_tool to retrieve the weather information for any given location. 
        b) If the question is regular conversaion, respond naturally and conversationally as no information retrieval is needed.
        c) Try to answer based on your internal knowledge.
        d) If NONE of the THE ABOVE works, say 'I Don't know the answer'.      
    '''

    return prompt_dict.get(prompt_name, 'Invalid prompt passed')

def get_chat_model() -> ChatOpenAI:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    openai_api_key = os.environ['OPENAI_API_KEY']
    chat_model = ChatOpenAI(
        model= 'gpt-4o-mini',
        temperature=0.3,
        api_key=openai_api_key
    )
    log.info('Retrieved the chat model')
    return chat_model

async def check_tool_condition(state: RagState):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    if state.get('tool_execution_count',0) >= 5:
        return 'end'
    last_AIMessage = state['messages'][-1]
    tool_calls = getattr(last_AIMessage, 'tool_calls', None)
    if tool_calls:
        return 'node_tool_execution'
    else:
        return 'end'

def build_tools(mcp_server: FastMCP):
    @tool
    async def get_weather_tool(city: str):
        '''
        Docstring for weather_tool
        :param city: Input city whose weather is being requested for.
        :type city: str

        This function tool get the city name as the input and returns the current weather information for that city
        '''
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_server.call_tool(
                                            name = 'get_weather',
                                            arguments = {'city':city}
                )
        try:
            log.info(f'response retrieved inside build_tools is {resp[0].text}')         
            resp_content = WeatherDataResponse.model_validate_json(resp[0].text)
        except Exception as err:
            log.info(f'Errored in {inspect.currentframe().f_code.co_name} with error {err}')
            return WeatherDataResponse()
        
        return resp_content
    
    @tool
    async def get_employee_master_record(employee_id:str):
        '''
        Docstring for get_employee_master_record
        
        :param employee_id: This function takes the Employee ID as a parameter and returns the employee details from the Cosmos DB Database.
        :type employee_id: str
        '''
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_server.call_tool(
                                            name = 'get_employee_master_record',
                                            arguments = {'employee_id':employee_id}
                )
        try:
            log.info(f'response retrieved inside build_tools is {resp[0].text}') 
            resp_content = EmployeeMasterResponseModel.model_validate_json(resp[0].text)
        except Exception as err:
            log.info(f'Errored in {inspect.currentframe().f_code.co_name} with error {err}')
            return EmployeeMasterResponseModel()
        
        return resp_content
    
    # @tool
    # async def get_employee_leave_record(employee_id:str):
    #     '''
    #     Docstring for get_employee_leave_record
        
    #     :param employee_id: This function takes the employee ID as a parameter and returns that employees leave information from Cosmos DB Database.
    #     :type employee_id: str
    #     '''

    #     log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    #     resp = await MCP_SESSION.call_tool(
    #                                         name = 'get_employee_leave_record',
    #                                         arguments = {'employee_id':employee_id}
    #             )

    #     try:
    #         resp_content = EmployeeLeaveResponseModel.model_validate_json(resp.content[0].text)
    #     except:
    #         return None
        
    #     return resp_content
    
    @tool
    async def get_rag_document_tool(inp_question:str):
        '''
        Docstring for get_leave_policy_document
        
        :param inp_question: This function gets the input question and then checks whether the information is present in the Azure AI Search vector DB and return the best possible result back. This does an vector embedding similarity 
        search by calling the MCP tool function get_rag_document.
        :type inp_question: str
        '''
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_server.call_tool(
                                    name='get_rag_document',
                                    arguments={'inp_question':inp_question}
        )
        try:
            log.info(f'response retrieved inside build_tools is {resp[0].text}') 
            resp_content = RagDataResponseModel.model_validate_json(resp[0].text)
        except Exception as err:
            log.info(f'Errored in {inspect.currentframe().f_code.co_name} with error {err}')
            return RagDataResponseModel()
        
        return resp_content

    return [get_weather_tool, get_rag_document_tool]

def build_nodes(llm_with_tools):

    async def node_generate_answer_from_llm(state:RagState):
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

        inp_system_message = get_prompts('input_prompt_system')
        inp_human_message = get_prompts('input_prompt_human', question=state.get('question', ''))
        SYSTEM_MESSAGE = SystemMessage(content=inp_system_message)
        HUMAN_MESSAGE = HumanMessage(content=inp_human_message)
        response = await llm_with_tools.ainvoke(state['messages'] + [SYSTEM_MESSAGE, HUMAN_MESSAGE])
        count = state.get('tool_execution_count',0)
        if getattr(response, 'tool_calls', None):
            count += 1

        return {
        'messages':[HUMAN_MESSAGE, response],
        'tool_execution_count' : count
        }
    
    return {
        'node_generate_answer_from_llm' : node_generate_answer_from_llm
    }

def recreate_index(index_name:str):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    index_client = SearchIndexClient(
        endpoint=azure_ai_search_endpoint,
        credential=DefaultAzureCredential()
    )
    try:
        index_client.delete_index(index=index_name)
        log.info(f'CUSTOM LOG - Deleted Index : {index_name}')
    except Exception as err:
        log.info(f'CUSTOM LOG - Index {index_name} not deleted because of error {err}')

    with open('utils/create_index.json', 'r') as f:
        index_schema = json.load(f)

    index_schema = SearchIndex.from_dict(index_schema)
    index_client.create_index(index=index_schema)

    log.info(f'CUSTOM LOG - Index {index_schema} created successfully')

def get_azure_openai_client() -> AzureOpenAI:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    credential = DefaultAzureCredential()
    token_provider = lambda: credential.get_token(
        "https://cognitiveservices.azure.com/.default"
    ).token
    endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')
    client = AzureOpenAI(api_version="2024-12-01-preview",azure_endpoint=endpoint, azure_ad_token_provider=token_provider)

    return client

def generate_embeddings(doc_chunks:List[Document]) -> List:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    vector_db_index_list = []
    openai_client = get_azure_openai_client()

    for i, doc_chunk in enumerate(doc_chunks):
        embedding = openai_client.embeddings.create(
            model='text-embedding-3-small',
            input=doc_chunk.page_content
        )
        vector_db_index = {
            'id' : f'{doc_chunk.metadata.get('metadata_doc_name')}_{i}',
            'metadata_section_id' : doc_chunk.metadata.get('metadata_section_id'),
            'metadata_title' : doc_chunk.metadata.get('metadata_title'),
            'metadata_doc_name' : doc_chunk.metadata.get('metadata_doc_name'),
            'content_text' : doc_chunk.page_content,
            'embedding' : embedding.data[0].embedding
        }
        vector_db_index_list.append(vector_db_index)
        # break

    return vector_db_index_list

def write_embeddings(vector_db_index_list : List[Dict]):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    index_name='leave_agent_vector_index'
    recreate_index(index_name)
    azure_ai_search_client = SearchClient(
                            endpoint=azure_ai_search_endpoint,
                            index_name=index_name,
                            credential= DefaultAzureCredential()
                            )
    result = azure_ai_search_client.upload_documents(vector_db_index_list)
    for r in result:
        log.info(f'CUSTOM LOG - response after uploading index document is {r}')
    log.info(f'CUSTOM LOG - Embeddings written successfully')

def getAzureSecrets(key:str) -> str:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=VAULT_URL, credential=credential)
    client_secret = client.get_secret(key).value

    return client_secret

def get_chunks(file_data:List[Document], file_name:str) -> List[Document]:
    file_path = Path(file_name)
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    full_text = ''
    for doc in file_data:
        full_text += doc.page_content

    pattern = r'(?m)^[•]?\s*(\d+(?:\.\d+)+)\s+([^\n]+)'
    matches = list(re.finditer(pattern, full_text))

    langchain_doc = []

    for i, match in enumerate(matches):
        section_id = match.group(1)
        title = match.group(2).strip()

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)

        content = full_text[start:end].strip()
        if content:
            page_content = f'{section_id} {title}\n{content}'
            metadata = {
                'metadata_section_id' : section_id,
                'metadata_title' : title,
                'metadata_doc_name' : file_path.stem.replace(' ', '')
            }
            langchain_doc.append(
                Document(page_content=page_content, metadata=metadata)
            )

    return langchain_doc