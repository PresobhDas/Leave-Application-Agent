from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils import get_chat_model, get_mcp_session, get_weather_tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import logging, sys

log = logging.getLogger('api')
log.setLevel(logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s"
)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

api_server = FastAPI()

class InputDetails(BaseModel):
    inp_query:str

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.post('/agent')
async def call_agent(inp_details : Annotated[InputDetails, Body()]):
    log.info('Function Invoked')
    class RagState(StateGraph):
        question:str
        tool_execution_count: int

    log.info('CUSTOM LOG : Calling the call_agent function for processing the request')
    chat_model = get_chat_model()
    MCP_SESSION = get_mcp_session()

    async def check_tool_condition(state: RagState):
        log.info('Function Invoked')
        if state.get('tool_execution_count',0) >= 5:
            return 'end'
        last_AIMessage = state['messages'][-1]
        tool_calls = getattr(last_AIMessage, 'tool_calls', None)
        if tool_calls:
            return 'tool_execution_node'
        else:
            return 'end'

    async def generate_answer_from_llm(state:RagState):
        log.info('Function Invoked')
        inp_system_message = await MCP_SESSION.get_prompt(
            name = 'get_input_prompt_system'
        )
        inp_human_message = await MCP_SESSION.get_prompt(name='get_input_prompt_human',
                        arguments={
                                        'question' : state.question,
                                        'context' : ''
                                    } 
                )
        SYSTEM_MESSAGE = SystemMessage(content=inp_system_message.messages[0].content.text)
        HUMAN_MESSAGE = HumanMessage(content=inp_human_message.messages[0].content.text)
        response = await answer_llm_with_tools.ainvoke(state['messages'] + [SYSTEM_MESSAGE, HUMAN_MESSAGE])
        count = state.get('tool_execution_count',0)
        if getattr(response, 'tool_calls', None):
            count += 1

        return {
        'messages':[HUMAN_MESSAGE, response],
        'tool_execution_count' : count
        }

    tools = [get_weather_tool]
    answer_llm_with_tools = chat_model.bind_tools(tools)
    graph = StateGraph(RagState)

    graph.add_node('generate_answer_from_llm', generate_answer_from_llm)
    tool_execution_node = ToolNode(tools=tools)
    graph.add_node('tool_execution_node', tool_execution_node)

    graph.add_edge(START, 'generate_answer_from_llm')
    graph.add_conditional_edges(
        'generate_answer_from_llm',
        check_tool_condition,
        {
            'tool_execution_node': 'tool_execution_node',
            'end': END
        }
    )
    graph_app = graph.compile()
    log.info('Graph created and compiled')
    result = await graph_app.ainvoke(
        {
            'question' : inp_details.inp_query,
            'tool_execution_count' : 0
        }
    )

    return result


