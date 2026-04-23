import logging, sys, inspect, os, tempfile, json
from fastapi import FastAPI, Body, Request
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils.llm_utils import get_chat_model, build_nodes, check_tool_condition, build_tools, get_chunks, generate_embeddings, write_embeddings, RagState
from utils.model_contracts import InputDetails, UploadRequest
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from api_func.mcp_app import register_tools
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from langchain_community.document_loaders import PyPDFLoader
from urllib.parse import urlparse, unquote
from fastapi.middleware.cors import CORSMiddleware
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import _ContextPrecision, _ContextRecall, _ContextRelevance

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.ERROR)

if not log.handlers:
    h = logging.StreamHandler(sys.stdout) 
    h.setLevel(logging.INFO)
    log.addHandler(h)

api_server = FastAPI()
api_server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mcp = FastMCP(
                name="Leave-application-mcp-server",
                transport_security=TransportSecuritySettings(
                    enable_dns_rebinding_protection=True,
                    allowed_hosts=["*"]  # relaxed since internal now
                )
            )

rag_retreival_function = register_tools(mcp)
chat_model = get_chat_model()
mcp_server = mcp.streamable_http_app()
api_server.mount("/mcp", mcp_server)

@api_server.get('/ping')
async def ping():
    return {'response':'pong'}

@api_server.post('/get-upload-url')
def get_upload_url(req: UploadRequest):
    filename = req.filename
    ACCOUNT_NAME = 'leaveagentaccount'
    CONTAINER = 'rag-docs'
    sas = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=CONTAINER,
        blob_name=filename,
        account_key=os.environ.get('STORAGE_ACCOUNT_KEY'),
        permission=BlobSasPermissions(write=True, create=True),
        expiry=datetime.utcnow() + timedelta(minutes=10),
    )

    url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{CONTAINER}/{filename}?{sas}"
    return {"uploadUrl": url}

@api_server.post('/ingest')
async def ingest_pipeline(request:Request):
    try:
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        events = await request.json()
        event = events[0]
        if event['eventType'] == 'Microsoft.EventGrid.SubscriptionValidationEvent':
            validation_code = event['data']['validationCode']
            return {
                'validationResponse' : validation_code
            }
        
        if event['eventType'] == 'Microsoft.Storage.BlobCreated':
            log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name} followed by the event of BLOB file creation')
            blob_url = event['data']['url']

            parsed = urlparse(blob_url)
            path_parts = parsed.path.lstrip('/').split('/', 1)
            container_name = path_parts[0]
            blob_name = unquote(path_parts[1])
            file_extension = os.path.splitext(os.path.basename(parsed.path))[1]

            log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name} with container name : {container_name}, blob name : {blob_name}, file extension : {file_extension}')

            blob_service_client = BlobServiceClient(
                        account_url = f"{parsed.scheme}://{parsed.netloc}",
                        credential = DefaultAzureCredential()
                    )

            blob_client = blob_service_client.get_blob_client(
                container=container_name,
                blob=blob_name
            )
            pdf_bytes = blob_client.download_blob().readall()
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(pdf_bytes)
                temp_path = temp_file.name
            loader = PyPDFLoader(file_path=temp_path)
            docs = loader.load()
            doc_chunks = get_chunks(docs, blob_name)

            log.info(f'CUSTOM LOG - {len(doc_chunks)} chunks retrieved')
            embedding_list = generate_embeddings(doc_chunks)
            write_embeddings(embedding_list)

    except Exception as err:
        log.exception(f'CUSTOM LOG - Exception occurred at {inspect.currentframe().f_code.co_name}')
        return {'status' : 'Errored'}



    return {'status' : 'uploaded'}

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

@api_server.post('/evaluate')
async def call_evaluate():
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

    try:
        with open('utils/leave_policy_litigation_dataset.json', 'r') as f:
            dataset_list = json.load(f)

        ragas_data = {
            'question' : [],
            'contexts' : [],
            'ground_truth' : []
        }

        for item in dataset_list:
            ragas_data["question"].append(item["question"])
            ragas_data["ground_truth"].append(item["groundtruth"])
            resp = await rag_retreival_function(inp_question = ragas_data["question"])
            ragas_data['contexts'].append(resp)

        log.info(f'CUSTOM LOG - ragas data is {ragas_data}')
        dataset = Dataset.from_dict(ragas_data)

        results = evaluate(
            dataset,
            metrics=[
                    _ContextPrecision,
                    _ContextRecall,
                    _ContextRelevance
                ]
        )
        log.info(f'CUSTOM LOGS - RAGAS result is {results}')
        return results

    except Exception:
        log.exception(f'CUSTOM LOG - Errored in {inspect.currentframe().f_code.co_name}')
    




