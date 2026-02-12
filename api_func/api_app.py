from fastapi import FastAPI, Body
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils.llm_utils import get_chat_model, build_nodes, build_tools, check_tool_condition, RagState, InputDetails
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import logging, sys, inspect, os
import httpx, asyncio

log = logging.getLogger('api')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

api_server = FastAPI()

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.post('/agent')
async def call_agent(inp_details : Annotated[InputDetails, Body()]):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    async def process_ai_agent():
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

        tools = build_tools(MCP_SESSION)
        llm_with_tools = chat_model.bind_tools(tools)
        nodes = build_nodes(MCP_SESSION, llm_with_tools)

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
    MCP_SERVER = os.environ['MCP_SERVER_ENDPOINT']
    async def probe():
        async with httpx.AsyncClient(follow_redirects=False, timeout=20.0) as client:
            r = await client.get(MCP_SERVER, headers={"Accept": "text/event-stream"})
            log.info("status:", r.status_code)
            log.info("location:", r.headers.get("location"))
            log.info("content-type:", r.headers.get("content-type"))
            log.info("mcp-session-id:", r.headers.get("mcp-session-id"))
            log.info("first100:", r.text[:100])

    await probe()
    try:
        async with streamable_http_client(MCP_SERVER) as (read, write, session_id):
            async with ClientSession(read, write) as MCP_SESSION:
                await MCP_SESSION.initialize()
                log.info('CUSTOM LOG - Created MCP_SESSION')
                result = await process_ai_agent()
                return result
    except* Exception as e:
        log.exception(f'Failed with Exception: {e.exceptions}')




