import logging, sys, inspect, os, tempfile, json, math
from fastapi import FastAPI, Body, Request
from typing import Annotated
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from utils.llm_utils import get_chat_model, build_nodes, check_tool_condition, build_tools, get_chunks, generate_embeddings, write_embeddings, get_azure_openai_client, delete_existing_embeddings, node_capture_rag_context, write_ragas_with_session_history
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
from azure.cosmos import CosmosClient
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
    graph.add_node('node_capture_rag_context', nodes['node_capture_rag_context'])
    graph.add_node('node_decompose_question', nodes['node_decompose_question'])
    graph.add_node('node_pick_next_question', nodes['node_pick_next_question'])
    graph.add_node('node_collect_sub_answer', nodes['node_collect_sub_answer'])
    graph.add_node('node_synthesize_final', nodes['node_synthesize_final'])

    graph.add_edge(START, 'node_generate_answer_from_llm')
    graph.add_conditional_edges(
        'node_pick_next_question',
        lambda state: "process" if state.get("current_sub_question") else "done",
        {
            "process": "node_generate_answer_from_llm",
            "done": "node_synthesize_final"
        }
    )
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
    graph.add_edge('node_collect_sub_answer', 'node_pick_next_question')
    graph.add_edge('node_synthesize_final', END)

    graph_app = graph.compile()
    log.info(f'CUSTOM LOG - Graph compiled and created inside : {inspect.currentframe().f_code.co_name}')
    result = await graph_app.ainvoke(
        {
            'userId' : inp_details.user_id,
            'question' : inp_details.inp_query,
            'tool_execution_count' : 0
        }
    )

    ragas_data = await write_ragas_with_session_history(result)

    return {
        'llmResponse' : ragas_data.ragasInp.llmResponse,
        'confidence' : sum(ragas_data.ragasInp.confidenceScore) / len(ragas_data.ragasInp.confidenceScore) * 100
    }

@api_server.get('/history')
async def get_history(user_id: str):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    try:
        # 🔐 Cosmos client (Managed Identity)
        client = CosmosClient(
            url=os.environ["COSMOS_DB_CONN_STR"],
            credential=DefaultAzureCredential()
        )

        container = client.get_database_client("session_history").get_container_client("user_session")

        # 🔍 Query (partition key = sessionId = user_id)
        query = """
        SELECT c.ragasInp.inpQuestion, c.ragasInp.llmResponse, c.ragasInp.confidenceScore, c.timestamp
        FROM c
        WHERE c.user_id = @user_id
        ORDER BY c.timestamp ASC
        """

        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@user_id", "value": user_id}],
            enable_cross_partition_query=False  # efficient if partition key is correct
        ))

        history = []

        for item in items:
            scores = item.get("confidenceScore", [])

            avg_conf = sum(scores) / len(scores) * 100 if scores else 0.0

            history.append({
                "question": item.get("inpQuestion", ""),
                "answer": item.get("llmResponse", ""),
                "confidence": avg_conf
            })

        return history

    except Exception as err:
        log.exception(f'CUSTOM LOG - Errored in {inspect.currentframe().f_code.co_name} with error {err}')
        return []

@api_server.get('/evaluate')
async def call_evaluate():
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    try:
        client = CosmosClient(
            url=os.environ["COSMOS_DB_CONN_STR"],
            credential=DefaultAzureCredential()
        )

        container = client.get_database_client("session_history").get_container_client("user_session")
        items = list(container.read_all_items())

        faithfulness_list = [item.get('ragasMetrics').get('faithfulness', 0.0) for item in items]
        relevancy_list = [item.get('ragasMetrics').get('relevancy', 0.0) for item in items]

        return {
            'faithfulness' : sum(faithfulness_list) / len(faithfulness_list),
            'relevancy' : sum(relevancy_list) / len(relevancy_list)
        }        

    except Exception as err:
        log.exception(f'CUSTOM LOG - Errored in {inspect.currentframe().f_code.co_name} with error {err}')
    




