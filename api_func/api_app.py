from fastapi import FastAPI, Body, Request
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils.llm_utils import get_chat_model, build_nodes, build_tools, check_tool_condition, RagState
from utils.model_contracts import InputDetails
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import logging, sys, inspect, os
import uuid

log = logging.getLogger('api')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

log.propagate = False
log.info(f"LOGGER_DIAG handlers={len(log.handlers)} handler_ids={[id(h) for h in log.handlers]}")

api_server = FastAPI()

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.post('/agent')
async def call_agent(request:Request, inp_details : Annotated[InputDetails, Body()]):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    rid = str(uuid.uuid4())
    log.info(f"RID={rid} Entered call_agent client={request.client} ua={request.headers.get('user-agent')} xff={request.headers.get('x-forwarded-for')}")
    async def process_ai_agent():
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

        tools = build_tools(MCP_SERVER)
        llm_with_tools = chat_model.bind_tools(tools)
        nodes = build_nodes(llm_with_tools)

        graph = StateGraph(RagState)
        graph.add_node('node_generate_answer_from_llm', nodes['node_generate_answer_from_llm'])
        node_tool_execution = ToolNode(tools=tools)
        graph.add_node('node_tool_execution', node_tool_execution)
        graph.add_edge(START, 'node_generate_answer_from_llm')
        graph.add_conditional_edges(
            'node_generate_answer_from_llm',
            check_tool_condition,
            {
                'node_tool_execution': 'node_tool_execution',
                'end': END
            }
        )
        graph.add_edge('node_tool_execution', 'node_generate_answer_from_llm')
        graph_app = graph.compile()
        log.info('Graph created and compiled')
        result = await graph_app.ainvoke(
            {
                'question' : inp_details.inp_query,
                'tool_execution_count' : 0
            }
        )

        return result

    log.info('Function Invoked')

    chat_model = get_chat_model()
    MCP_SERVER = f'{os.environ['MCP_SERVER_ENDPOINT']}/runtime/webhooks/mcp?code={os.environ['MCP_EXTENSION_KEY']}'
    log.info(f'MCP_SERVER is at {MCP_SERVER}')
    try:
        # async with streamable_http_client(MCP_SERVER) as (read, write, session_id):
        #     async with ClientSession(read, write) as MCP_SESSION:
        #         await MCP_SESSION.initialize()
        #         log.info('CUSTOM LOG - Created MCP_SESSION')
        result = await process_ai_agent()
        return result
    except* Exception as e:
        log.exception(f'Failed with Exception: {e.exceptions}')




