import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
import logging, sys, inspect
from mcp import ClientSession
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel

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
        resp_content = WeatherData.model_validate_json(resp.content[0].text)
        log.info(f'Formatted resp_content is {resp_content}')
        return resp_content
    
    return [get_weather_tool]

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