import os, logging, sys, inspect
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from mcp import ClientSession
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel
from huggingface_hub import InferenceClient

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

class InputDetails(BaseModel):
    inp_query:str

def get_chat_model() -> ChatOpenAI:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    chat_model = ChatOpenAI(
        model= 'gpt-4o-mini',
        temperature=0.3,
        api_key=os.environ['OPENAI_API_KEY']
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
    @tool
    async def get_weather_tool(city: str):
        '''
        Docstring for weather_tool
        :param city: Input city whose weather is being requested for.
        :type city: str

        This function tool get the city name as the input and returns the current weather information for that city
        '''

        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_session.call_tool(
                                            name = 'get_weather',
                                            arguments = {'city':city} 
                        )   
        try:
            resp_content = WeatherData.model_validate_json(resp.content[0].text)
        except:
            return None
        
        return resp_content
    
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

    return [get_weather_tool, get_employee_master_record, get_employee_leave_record]

def build_nodes(mcp_session:ClientSession, llm_with_tools):

    async def node_generate_answer_from_llm(state:RagState):
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        inp_system_message = await mcp_session.get_prompt(
            name = 'get_input_prompt_system'
        )
        inp_human_message = await mcp_session.get_prompt(name='get_input_prompt_human',
                        arguments={
                                        'question' : state.get('question', ''),
                                        'context' : ''
                                    } 
                )
        SYSTEM_MESSAGE = SystemMessage(content=inp_system_message.messages[0].content.text)
        HUMAN_MESSAGE = HumanMessage(content=inp_human_message.messages[0].content.text)
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
    SENTENCE_TRANSFORMER_TOKEN = os.environ['SENTENCE_TRANSFORMER_TOKEN']
    client = InferenceClient(model='BAAI/bge-base-en-v1.5', token=SENTENCE_TRANSFORMER_TOKEN)
    embeddings = client.feature_extraction(text=text_chunk)

    return embeddings