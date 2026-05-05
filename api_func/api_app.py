import logging, sys, inspect, os, tempfile, json, math
from fastapi import FastAPI, Body, Request
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils.llm_utils import get_chat_model, build_nodes, check_tool_condition, build_tools, get_chunks, generate_embeddings, write_embeddings, get_azure_openai_client, get_llm_answer_for_ragas, delete_existing_embeddings, node_capture_rag_context
from utils.model_contracts import InputDetails, UploadRequest, RagState
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from api_func.mcp_app import register_tools
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from urllib.parse import urlparse, unquote
from fastapi.middleware.cors import CORSMiddleware
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import _ContextPrecision, _ContextRecall, _ContextRelevance, _Faithfulness, _ResponseRelevancy
from utils.model_contracts import RagDataResponseModel
from azure.ai.documentintelligence import DocumentIntelligenceClient

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
            file_name = os.path.splitext(os.path.basename(parsed.path))[0].replace(' ', '')
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

            DI_ENDPOINT = os.getenv('DI_ENDPOINT')
            di_client = DocumentIntelligenceClient(endpoint=DI_ENDPOINT, credential=DefaultAzureCredential())
            with open(temp_path, "rb") as f:
                poller = di_client.begin_analyze_document(
                    model_id="prebuilt-layout",
                    body=f,   
                    content_type="application/pdf"   
                )

            result = poller.result().as_dict()
            json_di = json.dumps(result, indent=2)
            json_blob_client = blob_service_client.get_blob_client(
                container='rag-docs-json',
                blob=f'{file_name}.json'
            )

            json_blob_client.upload_blob(
                json_di,
                overwrite=True
            )

            log.info(f'CUSTOM - LOG : JSON written into {temp_file}.json')

            delete_existing_embeddings(file_name=file_name)
            doc_chunks = get_chunks(json.loads(json_di), file_name=file_name)
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
    graph.add_node('node_tool_execution', ToolNode(tools=tools))
    graph.add_node('node_capture_rag_context', node_capture_rag_context)

    graph.add_edge(START, 'node_generate_answer_from_llm')
    graph.add_conditional_edges(
        'node_generate_answer_from_llm',
        check_tool_condition,
        {
            'node_tool_execution': 'node_tool_execution',
            'end': END
        }
    )
    graph.add_edge('node_tool_execution', 'node_capture_rag_context')
    graph.add_edge('node_capture_rag_context', 'node_generate_answer_from_llm')
    graph_app = graph.compile()
    log.info(f'CUSTOM LOG - Graph compiled and created inside : {inspect.currentframe().f_code.co_name}')
    result = await graph_app.ainvoke(
        {
            'question' : inp_details.inp_query,
            'tool_execution_count' : 0
        }
    )

    return result

@api_server.get('/evaluate')
async def call_evaluate():
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    try:
        blob_service_client = BlobServiceClient(
        account_url = os.environ.get('BLOB_ACCOUNT_URL'),
        credential = DefaultAzureCredential()
        )
        json_blob_client = blob_service_client.get_blob_client(
            container='ragas-json',
            blob='ragasmetrics.jsonl'
        )

        if json_blob_client.exists():
            blob_jsonl = json_blob_client.download_blob().readall().decode('utf-8')

        faithfulness_list = []
        relevancy_list = []
        for line in blob_jsonl.splitlines():
            line = line.strip()
            if not line:
                continue
            json_line = json.loads(line)
            faithfulness_line = json_line.get('ragasMetrics', {}).get('faithfulness', 0.0)
            relevancy_line = json_line.get('ragasMetrics', {}).get('relevancy', 0.0)

            if isinstance(faithfulness_line, float) and not math.isnan(faithfulness_line):
                faithfulness_list.append(faithfulness_line)
            if isinstance(relevancy_line, float) and not math.isnan(relevancy_line):
                relevancy_list.append(relevancy_line)

        if faithfulness_list:
            faithfulness_avg = sum(faithfulness_list) / len(faithfulness_list)

        if relevancy_list:
            relevancy_avg = sum(relevancy_list) / len(relevancy_list)

        log.info(f'CUSTOM LOG - Evaluation metrics. Faithfulness : {faithfulness_avg}, Relevancy : {relevancy_avg}')

        return {
            'faithfulness' : faithfulness_avg,
            'relevancy' : relevancy_avg
        }        

    except Exception:
        log.exception(f'CUSTOM LOG - Errored in {inspect.currentframe().f_code.co_name}')
    




