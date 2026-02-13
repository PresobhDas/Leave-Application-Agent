import os, logging, sys, inspect
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from mcp import ClientSession
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import json

VAULT_URL = "https://leave-policy-keyvault.vault.azure.net/"

log = logging.getLogger('utils')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

class RagState(MessagesState):
    question:str
    tool_execution_count: int

class WeatherData(BaseModel):
    latitude: float
    longitude: float
    temperature: float
    windspeed: float
    winddirection: float

class EmployeeData(BaseModel):
    id:str
    employeeId:str
    name:str
    department:str
    managerId:str
    hireDate:str
    workLocation:str
    isActive:bool

class EmployeeLeaveData(BaseModel):
    id:str
    employeeId:str
    name:str
    leaveType:str
    startDate:str
    endDate:str
    numberOfDays:int

class RagData(BaseModel):
    id:str
    partiion_key_id:str
    test:str
    matchPercent:int
class InputDetails(BaseModel):
    inp_query:str

tool_properties = dict()
tool_properties['get_employee_master_record'] = json.dumps([
  {"propertyName":"employee_id","propertyType":"string","description":"Employee ID","isRequired":True}
])

def get_prompts(prompt_name:str, question:str|None=None):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    prompt_dict = dict()

    prompt_dict['input_prompt_human'] = f"""This is the question : {question}."""
    prompt_dict['input_prompt_system'] = '''
    You are a helpful AI bot that does the following.
    1. Understand the question given to you by the user.
    2. Take the following actions ONLY with priority in the given order:
        a) If the question is regular conversaion, respond naturally and conversationally as no information retrieval is needed.
        b) Try to answer based on your internal knowledge.
        c) Call external tools provided to you. Details of the different tools ar as follows. There is NO particular order in which the below tools need to be invoked. Directly call the right tool as needed. No need to follow the below precedence.
            1) Tool Name : get_employee_master_record.
                Description: Retrieve the employee master information from the Azure Cosmos DB. This queries the NO SQL database based on the given Employee ID.
            2) Tool Name : get_employee_leave_record.
                Description: Retrieve the employee leave information from the Azure Cosmos DB. This queries the NO SQL database based on the given Employee ID.
            3) Tool Name : get_leave_policy_document.
                Description: This is the RAG retrieval tool and queries the Azure AI Search using the vector embeddings of the given input text based on similarity.
            4) Tool Name: get_weather_tool
                Description: get_weather_tool to retrieve the weather information for any given location. 
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

def build_tools(mcp_session:ClientSession):
    # @tool
    # async def get_weather_tool(city: str):
    #     '''
    #     Docstring for weather_tool
    #     :param city: Input city whose weather is being requested for.
    #     :type city: str

    #     This function tool get the city name as the input and returns the current weather information for that city
    #     '''

    #     log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    #     resp = await mcp_session.call_tool(
    #                                         name = 'get_weather',
    #                                         arguments = {'city':city} 
    #                     )   
    #     try:
    #         resp_content = WeatherData.model_validate_json(resp.content[0].text)
    #     except:
    #         return None
        
    #     return resp_content
    
    @tool
    async def get_employee_master_record(employee_id:str):
        '''
        Docstring for get_employee_master_record
        
        :param employee_id: This function takes the Employee ID as a parameter and returns the employee details from the Cosmos DB Database.
        :type employee_id: str
        '''
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_session.call_tool(
                                            name = 'get_employee_master_record',
                                            arguments = {'employee_id':employee_id}
        )
        try:
            resp_content = EmployeeData.model_validate_json(resp.content[0].text)
        except:
            return None
        
        return resp_content
    
    @tool
    async def get_employee_leave_record(employee_id:str):
        '''
        Docstring for get_employee_leave_record
        
        :param employee_id: This function takes the employee ID as a parameter and returns that employees leave information from Cosmos DB Database.
        :type employee_id: str
        '''

        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_session.call_tool(
                                            name='get_employee_leave_record',
                                            arguments={'employee_id':employee_id}
        )

        try:
            resp_content = EmployeeLeaveData.model_validate_json(resp.content[0].text)
        except:
            return None
        
        return resp_content
    
    # @tool
    # async def get_leave_policy_document(inp_question:str):
    #     '''
    #     Docstring for get_leave_policy_document
        
    #     :param inp_question: This function gets the input question and then checks whether the information is present in the Leave_Policy document and return the best possible result back. This does an vector embedding similarity 
    #     search.
    #     :type inp_question: str
    #     '''
    #     log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    #     resp = await mcp_session.call_tool(
    #                                 name='get_leave_policy_document',
    #                                 arguments={'inp_question':inp_question}
    #     )
    #     try:
    #         resp_content = RagData.model_validate_json(resp.content[0].text)
    #     except:
    #         return None
        
    #     return resp_content

    return [get_employee_master_record, get_employee_leave_record]

def build_nodes(mcp_session:ClientSession, llm_with_tools):

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

def generate_embeddings(text_chunk:str):
    from openai import AzureOpenAI

    credential = DefaultAzureCredential()
    endpoint = os.environ['AZURE_OPENAI_API_ENDPOINT']
    client = AzureOpenAI(api_version="2024-12-01-preview",azure_endpoint=endpoint, azure_ad_token_provider=credential)

    embedding = client.embeddings.create(
        model='text-embedding-3-small',
        input=text_chunk
    )

    return embedding.data[0].embedding

def getAzureSecrets(key:str) -> str:
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=VAULT_URL, credential=credential)
    client_secret = client.get_secret(key).value

    return client_secret