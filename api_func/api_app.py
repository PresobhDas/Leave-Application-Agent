import logging, sys, inspect, os, tempfile
from fastapi import FastAPI, Body, Request
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils.llm_utils import get_chat_model, build_nodes, check_tool_condition, build_tools, get_chunks, generate_embeddings, write_embeddings, RagState
from utils.model_contracts import InputDetails
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from api_func.mcp_app import register_tools
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from langchain_community.document_loaders import PyPDFLoader

log = logging.getLogger('api')
log.setLevel(logging.INFO)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

log.propagate = False
log.info(f"LOGGER_DIAG handlers={len(log.handlers)} handler_ids={[id(h) for h in log.handlers]}")

api_server = FastAPI()
mcp = FastMCP(
                name="Leave-application-mcp-server",
                transport_security=TransportSecuritySettings(
                    enable_dns_rebinding_protection=True,
                    allowed_hosts=["*"]  # relaxed since internal now
                )
            )

register_tools(mcp)
chat_model = get_chat_model()
mcp_server = mcp.streamable_http_app()
api_server.mount("/mcp", mcp_server)

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.post('/ingest')
async def ingest_pipeline():
    client = BlobServiceClient(
                account_url = os.environ.get('BLOB_ACCOUNT_URL'),
                credential = DefaultAzureCredential()
            )
    container = client.get_container_client("rag-docs")

    for blob in container.list_blobs():
        blob_client = container.get_blob_client(blob=blob.name)
        pdf_bytes = blob_client.download_blob().readall()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_path = temp_file.name
        loader = PyPDFLoader(file_path=temp_path)
        docs = loader.load()
        doc_chunks = get_chunks(docs, blob.name)

    embedding_list = generate_embeddings(doc_chunks)
    write_embeddings(embedding_list)

    return {'status' : 'ok'}

@api_server.post('/agent')
async def call_agent(request:Request, inp_details : Annotated[InputDetails, Body()]):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    tools = build_tools(mcp_server=mcp)
    log.info(f'CUSTOM LOG - Retrieved tools inside : {inspect.currentframe().f_code.co_name}')

    llm_with_tools = chat_model.bind_tools(tools=tools)
    nodes = build_nodes(llm_with_tools)
    log.info(f'CUSTOM LOG - Nodes built inside : {inspect.currentframe().f_code.co_name}')

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
    log.info(f'CUSTOM LOG - Graph compiled and created inside : {inspect.currentframe().f_code.co_name}')
    result = await graph_app.ainvoke(
        {
            'question' : inp_details.inp_query,
            'tool_execution_count' : 0
        }
    )

    return result




