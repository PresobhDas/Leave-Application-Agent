import httpx
from fastapi import FastAPI, Body, Request
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils.llm_utils import get_chat_model, build_nodes, build_tools, check_tool_condition, RagState
from utils.model_contracts import InputDetails
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import logging, sys, inspect, os
import uuid, asyncio

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
    async def process_ai_agent(MCP_SESSION):
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

        tools = build_tools(MCP_SESSION)
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

    async def call_mcp():
        async with streamable_http_client(url=MCP_SERVER) as (read_stream, write_stream, _):
            async with ClientSession(read_stream=read_stream, write_stream=write_stream) as MCP_SESSION:
                await MCP_SESSION.initialize()
                result = await process_ai_agent(MCP_SESSION)
        return result

    MAX_RETRIES = 3
    TIMEOUT = 10
    chat_model = get_chat_model()
    MCP_SERVER = os.environ['MCP_SERVER_ENDPOINT']
    headers = {"x-functions-key": os.environ['MCP_FUNCTION_KEY']}
    log.info(f'MCP_SERVER is at {MCP_SERVER}')

    for attempt in range(MAX_RETRIES):
        try:
            return await asyncio.wait_for(call_mcp(), timeout=TIMEOUT)
        except asyncio.TimeoutError:
            log.warning(f'Timeout while trying to connect to the MCP server at attempt {attempt+1}')
        except Exception as err:
            log.warning(f'Errored with exception {err} at attempt {attempt+1}')



