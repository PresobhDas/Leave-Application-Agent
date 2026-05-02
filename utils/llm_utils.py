import os, logging, sys, inspect, re, json, hashlib
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import MessagesState
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from utils.model_contracts import EmployeeMasterResponseModel, EmployeeLeaveResponseModel, WeatherDataResponse, RagDataResponseModel, RagasInp, RagasMetrics, RagasData
from mcp.server.fastmcp import FastMCP
from typing import List, Dict
from langchain_core.documents import Document
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex
from openai import AzureOpenAI
from pathlib import Path
from azure.ai.textanalytics import TextAnalyticsClient
from azure.data.tables import TableClient
from azure.core.exceptions import ResourceNotFoundError
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import _Faithfulness, _ResponseRelevancy
from ragas.llms import LangchainLLMWrapper
from langchain_openai import OpenAIEmbeddings as LCOpenAIEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper 
from azure.storage.blob import BlobServiceClient

VAULT_URL = os.environ.get('VAULT_URL')

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

azure_ai_search_endpoint = os.environ.get('AZURE_AI_SEARCH_CONNECTION_STRING')
class RagState(MessagesState):
    question:str
    tool_execution_count: int

def get_prompts(prompt_name:str, question:str|None=None):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    prompt_dict = dict()

    prompt_dict['input_prompt_human'] = f"""This is the question : {question}."""
    prompt_dict['input_prompt_system'] = '''
    You are a helpful AI bot that does the following.
    1. Understand the question given to you by the user.
    2. Take the following actions ONLY with priority in the given order:
        a) Call external tools provided to you. Details of the different tools ar as follows. There is NO particular order in which the below tools need to be invoked. Directly call the right tool as needed. No need to follow the below precedence. If tools returns 'NOT FOUND', quit retrying and exit with the proper response of not getting data from that particular tool.
            1) Tool Name : get_employee_master_record_tool.
                Description: Retrieve the employee master information from the Azure Storage Account Table. This queries the table on the given Employee ID.
            2) Tool Name : get_employee_leave_record_tool.
                Description: Retrieve the employee leave information from the Azure Storage Account Table. This queries the table on the given Employee ID.
            3) Tool Name : get_rag_document_tool.
                Description: If the question is about compensation, payroll, Health, Insurance, Leave Policy or anything in general about HR and company policies, call the RAG retrieval tool and queries the Azure AI Search using the vector embeddings of the given input text based on similarity.
                IMPORTANT: When using the results from this tool:
                - You MUST cite sources using [Source X] in the answer.
                - You MUST include the document Title (title).
                - You MUST include the document name (docName).
            4) Tool Name: get_weather_tool
                Description: get_weather_tool to retrieve the weather information for any given location. 
        b) If the question is regular conversaion, respond naturally and conversationally as no information retrieval is needed.
        c) Try to answer based on your internal knowledge. Do this ONLY if tool call is NOT applicable.
        d) If NONE of the THE ABOVE works, say 'I Don't know the answer'.     
    '''

    return prompt_dict.get(prompt_name, 'Invalid prompt passed')

def get_chat_model() -> ChatOpenAI:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    openai_api_key = os.environ['OPENAI_API_KEY']
    chat_model = ChatOpenAI(
        model= 'gpt-4o-mini',
        temperature=0.3,
        api_key=openai_api_key
    )
    log.info('Retrieved the chat model')
    return chat_model

def redact_pii(content_to_redact:Dict):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    try:
        def chunk_list(items, size=5):
            for i in range(0, len(items), size):
                yield items[i:i+size]

        PII_REDACTOR = os.environ.get('PII_REDACTOR')
        text_analytics_client = TextAnalyticsClient(
            endpoint=PII_REDACTOR,
            credential=DefaultAzureCredential()
        )
        texts_to_redact = []
        all_results = []

        for key, val in content_to_redact.get('employee').items():
            if isinstance(val, int) or isinstance(val, str):
                texts_to_redact.append(f'{key} - {val}')
        log.info(f'CUSTOM LOG - value of texts_to_redact is {texts_to_redact}')

        for chunk in chunk_list(texts_to_redact, size=5):
            response = text_analytics_client.recognize_pii_entities(
                chunk,
                categories_filter=["USSocialSecurityNumber", "Email"]
            )
            all_results.extend(response)

        for i, key in enumerate(content_to_redact.get('employee').keys()):
            if len(all_results[i].entities) > 0:
                content_to_redact['employee'][key] = '*' * len(content_to_redact['employee'][key])

    except Exception as err:
        log.info(f'CUSTOM LOG - Errored in {inspect.currentframe().f_code.co_name} with error {err}')

    return content_to_redact

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

def build_tools(mcp_server: FastMCP):
    @tool
    async def get_weather_tool(city: str):
        '''
        Docstring for weather_tool
        :param city: Input city whose weather is being requested for.
        :type city: str

        This function tool get the city name as the input and returns the current weather information for that city
        '''
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_server.call_tool(
                                            name = 'get_weather',
                                            arguments = {'city':city}
                )
        try:
            log.info(f'response retrieved inside build_tools is {resp[0].text}')         
            resp_content = WeatherDataResponse.model_validate_json(resp[0].text)
        except Exception:
            log.exception(f'Errored in {inspect.currentframe().f_code.co_name}')
            return WeatherDataResponse()
        
        return resp_content
    
    @tool
    async def get_employee_master_record_tool(employee_id:str):
        '''
        Docstring for get_employee_master_record
        
        :param employee_id: This function takes the Employee ID as a parameter and returns the employee details from Azure Storage Account table 'EmployeeMaster'
        :type employee_id: str
        '''
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_server.call_tool(
                                            name = 'get_employee_master_record',
                                            arguments = {'employee_id':employee_id}
                )
        try:
            log.info(f'response retrieved inside build_tools {inspect.currentframe().f_code.co_name} is {resp[0].text}') 
            resp_content = EmployeeMasterResponseModel.model_validate_json(json.dumps(redact_pii(json.loads(resp[0].text))))
        except Exception:
            log.exception(f'Errored in {inspect.currentframe().f_code.co_name}')
            return EmployeeMasterResponseModel()
        
        return resp_content
    
    @tool
    async def get_employee_leave_record_tool(employee_id:str):
        '''
        Docstring for get_employee_leave_record
        
        :param employee_id: This function takes the employee ID as a parameter and returns that employees leave information from Azure Storage Account table 'EmployeeLeaveMaster'
        :type employee_id: str
        '''

        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_server.call_tool(
                                            name = 'get_employee_leave_record',
                                            arguments = {'employee_id':employee_id}
                )

        try:
            log.info(f'response retrieved inside build_tools {inspect.currentframe().f_code.co_name} is {resp[0].text}') 
            resp_content = EmployeeLeaveResponseModel.model_validate_json(resp[0].text)
        except Exception:
            log.exception(f'Errored : {inspect.currentframe().f_code.co_name}')
            return EmployeeLeaveResponseModel()
        
        return resp_content
    
    @tool
    async def get_rag_document_tool(inp_question:str):
        '''
        Docstring for get_leave_policy_document
        
        :param inp_question: This function gets the input question and then checks whether the information is present in the Azure AI Search vector DB and return the best possible result back. This does an vector embedding similarity 
        search by calling the MCP tool function get_rag_document.
        :type inp_question: str
        '''
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
        resp = await mcp_server.call_tool(
                                    name='get_rag_document',
                                    arguments={'inp_question':inp_question}
        )
        try:
            return resp[0].text

        except Exception as err:
            log.info(f'Errored in {inspect.currentframe().f_code.co_name} with error {err}')
            return RagDataResponseModel()

    return [get_weather_tool, get_rag_document_tool, get_employee_master_record_tool, get_employee_leave_record_tool]

def build_nodes(llm_with_tools):

    async def node_generate_answer_from_llm(state:RagState):
        log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')

        inp_system_message = get_prompts('input_prompt_system')
        inp_human_message = get_prompts('input_prompt_human', question=state.get('question', ''))
        SYSTEM_MESSAGE = SystemMessage(content=inp_system_message)
        HUMAN_MESSAGE = HumanMessage(content=inp_human_message)
        response = await llm_with_tools.ainvoke(state['messages'] + [SYSTEM_MESSAGE, HUMAN_MESSAGE])
        log.info(f'CUSTOM LOG - THIS IS THE RESPONSE BACK FROM THE LLM CALL {response}')
        count = state.get('tool_execution_count',0)
        if getattr(response, 'tool_calls', None):
            count += 1
        
        ragas_data = None

        if not getattr(response, 'tool_calls', None):
            ragas_data = extract_ragas_data(state, response)

        return {
            'messages':[HUMAN_MESSAGE, response],
            'tool_execution_count' : count,
            'ragas_data': ragas_data  # optional: propagate forward
        }
    
    return {
        'node_generate_answer_from_llm' : node_generate_answer_from_llm
    }

def delete_existing_embeddings(file_name:str):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    index_name='leave_agent_vector_index'
    azure_ai_search_client = SearchClient(
                            endpoint=azure_ai_search_endpoint,
                            index_name=index_name,
                            credential= DefaultAzureCredential()
                            )
    
    results = azure_ai_search_client.search(
    search_text="*",
    filter=f"metadata_doc_name eq '{file_name}'",
    select=["id"]
    )

    to_delete = [{"id": r["id"]} for r in results]
    if to_delete:
        azure_ai_search_client.delete_documents(documents=to_delete)
        log.info(f'CUSTOM LOG : Existing embeddings deleted')
        return
    
    return log.info(f'CUSTOM LOG : No existing embeddings found to be deleted')

def recreate_index(index_name:str):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    index_client = SearchIndexClient(
        endpoint=azure_ai_search_endpoint,
        credential=DefaultAzureCredential()
    )
    try:
        index_client.delete_index(index=index_name)
        log.info(f'CUSTOM LOG - Deleted Index : {index_name}')
    except Exception as err:
        log.info(f'CUSTOM LOG - Index {index_name} not deleted because of error {err}')

    with open('utils/create_index.json', 'r') as f:
        index_schema = json.load(f)

    index_schema = SearchIndex.from_dict(index_schema)
    index_client.create_index(index=index_schema)

    log.info(f'CUSTOM LOG - Index {index_schema} created successfully')

def get_azure_openai_client() -> AzureOpenAI:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    credential = DefaultAzureCredential()
    token_provider = lambda: credential.get_token(
        "https://cognitiveservices.azure.com/.default"
    ).token
    endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')
    client = AzureOpenAI(api_version="2024-12-01-preview",azure_endpoint=endpoint, azure_ad_token_provider=token_provider)

    return client

def generate_embeddings(doc_chunks:List[Document]) -> List:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    vector_db_index_list = []
    openai_client = get_azure_openai_client()
    table_client = TableClient(
        endpoint=os.environ.get('TABLE_ACCOUNT_URL'),
        table_name='RagHash',
        credential=DefaultAzureCredential()
    )
    operations = []
    for i, doc_chunk in enumerate(doc_chunks):
        normalized_chunk = ' '.join(doc_chunk.page_content.strip().lower().split())
        chunk_hash = hashlib.sha256(normalized_chunk.encode('utf-8')).hexdigest()
        try:
            entity = table_client.get_entity('hashkey', chunk_hash)
        except ResourceNotFoundError:
            embedding = openai_client.embeddings.create(
                model='text-embedding-3-small',
                input=doc_chunk.page_content
            )
            vector_db_index = {
                'id' : f'{doc_chunk.metadata.get('metadata_doc_name')}_{i}',
                'metadata_section_id' : doc_chunk.metadata.get('metadata_section_id'),
                'metadata_title' : doc_chunk.metadata.get('metadata_title'),
                'metadata_doc_name' : doc_chunk.metadata.get('metadata_doc_name'),
                'content_text' : doc_chunk.page_content,
                'embedding' : embedding.data[0].embedding
            }
            vector_db_index_list.append(vector_db_index)
            log.info(f'CUSTOM LOG - hash for {doc_chunk.metadata.get('metadata_doc_name')}_{i} is {chunk_hash}')
            operations.append(('create', {"PartitionKey": "hashkey", "RowKey": chunk_hash}))
        else:
            log.info(f'CUSTOM LOG - Hash key for chunk {doc_chunk.metadata.get('metadata_doc_name')}_{i} already present. Skipping embedding')
    if operations:
        table_client.submit_transaction(operations=operations)
    return vector_db_index_list

def write_embeddings(vector_db_index_list : List[Dict]):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    if vector_db_index_list:
        index_name='leave_agent_vector_index'
        azure_ai_search_client = SearchClient(
                                endpoint=azure_ai_search_endpoint,
                                index_name=index_name,
                                credential= DefaultAzureCredential()
                                )
        result = azure_ai_search_client.upload_documents(vector_db_index_list)
        log.info(f'CUSTOM LOG - Embeddings written successfully')

def getAzureSecrets(key:str) -> str:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=VAULT_URL, credential=credential)
    client_secret = client.get_secret(key).value

    return client_secret

def get_chunks(di_data:dict, file_name:str) -> List[Document]:
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    langchain_doc = []
    paragraphs = di_data.get("paragraphs", [])

    # -------------------------------
    # Helpers
    # -------------------------------
    def extract_section_number(text):
        text = text.strip()

        # Strict pattern: only allow 1.0, 2.1, 2.1.3 etc
        match = re.match(r"^(\d+(\.\d+)+)\s+", text)

        if match:
            return match.group(1)
        return None

    def section_sort_key(section_number):
        return [int(x) for x in section_number.split('.')]

    def get_level(section_number):
        parts = section_number.split('.')
        if len(parts) == 2 and parts[1] == "0":
            return 1
        return len(parts)

    def get_parent_section(sec_num, section_map):
        parts = sec_num.split('.')
        while len(parts) > 1:
            parts.pop()
            parent = ".".join(parts)
            if parent + ".0" in section_map:
                return section_map[parent + ".0"]

            if parent in section_map:
                return section_map[parent]
        return None

    def is_probable_toc_line(text):
        # Detect TOC-like lines: "· 2.1 Something"
        return bool(re.match(r"^[\u2022\.\-]?\s*\d+(\.\d+)+\s+", text))
    # -------------------------------
    # Pass 1: Build section map
    # -------------------------------
    section_map = {}

    for para in paragraphs:
        text = para.get("content", "").strip()

        sec_num = extract_section_number(text)

        if sec_num:
            if len(text.split()) < 15:   # heuristic: headings are short
                section_map[sec_num] = text

    # -------------------------------
    # Pass 2: Chunking
    # -------------------------------
    chunks = []
    current_chunk = None

    for para in paragraphs:
        text = para.get("content", "").strip()
        role = para.get("role", "paragraph")

        if not text:
            continue

        sec_num = extract_section_number(text)

        # ---------------------------
        # New section
        # ---------------------------
        if role == "sectionHeading" and sec_num:
            parent = get_parent_section(sec_num, section_map)
            current_chunk = {
                "section_id": sec_num,
                "title": f"{parent} > {text}" if parent else text,
                "content": ""
            }
            chunks.append(current_chunk)
        # ---------------------------
        # Skip TOC-like junk
        # ---------------------------
        elif is_probable_toc_line(text):
            continue

        # ---------------------------
        # Append content
        # ---------------------------
        else:
            if current_chunk:
                if role == "listItem":
                    current_chunk["content"] += "• " + text + "\n"
                else:
                    current_chunk["content"] += text + "\n"

    # -------------------------------
    # Optional: Clean empty chunks
    # -------------------------------
    chunks = [c for c in chunks if c["content"].strip()]
    for chunk in chunks:
        page_content = f'{chunk['section_id']} {chunk['title']}\n{chunk['content']}'
        metadata = {
            'metadata_section_id' : chunk['section_id'],
            'metadata_title' : chunk['title'],
            'metadata_doc_name' : file_name
        }
        langchain_doc.append(
            Document(page_content=page_content, metadata=metadata)
        )

    return langchain_doc

def extract_ragas_data(state, response):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    try:
        question = state.get("question", "")
        messages = state["messages"]

        rag_msgs = [
            m for m in messages
            if isinstance(m, ToolMessage) and m.name == "get_rag_document_tool"
        ]

        if not rag_msgs:
            return None

        latest_tool_msg = rag_msgs[-1]

        try:
            parsed = RagDataResponseModel.model_validate_json(latest_tool_msg.content)
            contexts = [r.text for r in parsed.results]
        except Exception:
            contexts = []

        llm_answer = response.content if hasattr(response, "content") else str(response)

        ragas_inp = RagasInp(
            inpQuestion=question,
            retrievedContext=contexts,
            llmResponse=llm_answer
        )

        calculate_ragas_metrics(ragas_inp)

        log.info(f'RAGAS DATA CAPTURED: {ragas_inp.model_dump()}')
        return ragas_inp
    except Exception as err:
        log.info(f'CUSTOM LOG - Errored in {inspect.currentframe().f_code.co_name} with error {err}')

def calculate_ragas_metrics(ragas_inp : RagasInp):
    log.info(f'CUSTOM LOG - Entered : {inspect.currentframe().f_code.co_name}')
    try:
        chat_client = get_chat_model()

        llm = LangchainLLMWrapper(chat_client)
        embeddings = LangchainEmbeddingsWrapper(
        LCOpenAIEmbeddings(model="text-embedding-3-small")
        )
        dataset = Dataset.from_dict({
            "question": [ragas_inp.inpQuestion],
            "answer": [ragas_inp.llmResponse],
            "contexts": [ragas_inp.retrievedContext]
        })
        metrics = evaluate(dataset=dataset,
                metrics=[_Faithfulness, _ResponseRelevancy],
                llm=llm,
                embeddings=embeddings
        )
        scores = metrics._scores_dict
        ragas_metrics = RagasMetrics(
            faithfullness = scores.get('faithfulness', 0.0),
            relevancy = scores.get('answer_relevancy', 0.0)
        )

        ragas_data = RagasData(
            ragasInp=ragas_inp,
            ragasMetrics=ragas_metrics
        )

        blob_service_client = BlobServiceClient(
                account_url = os.environ.get('BLOB_ACCOUNT_URL'),
                credential = DefaultAzureCredential()
            )
        json_blob_client = blob_service_client.get_blob_client(
            container='ragas-json',
            blob=f'ragasmetrics.json'
        )

        try:
            json_blob_client.get_blob_properties()
        except:
            json_blob_client.create_append_blob()

        line = json.dumps(ragas_data.model_dump()) + "\n"
        json_blob_client.append_block(line.encode("utf-8"))

    except Exception as err:
        log.exception(f'Errored in {inspect.currentframe().f_code.co_name} with error : {err}')

def get_llm_answer_for_ragas(question:str, context:list):
    context_text = "\n\n".join(context)
    messages = [
    SystemMessage(content="You are an helpful AI Agent. Answer ONLY using the provided context. If unsure, say 'I don't know'."),
    HumanMessage(content=f"""
    Context:
    {context_text}

    Question:
    {question}
    """)
    ]

    open_ai_client = get_chat_model()
    response = open_ai_client.invoke(messages)

    return response.content