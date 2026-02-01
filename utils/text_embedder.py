from huggingface_hub import InferenceClient
from docx import Document
from langchain_text_splitters import TokenTextSplitter
from llm_utils import generate_embeddings
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient
import os

class MetaData(BaseModel):
    chunk_index:int
    heading:str
class DocChunk(BaseModel):
    id:str
    document_id:str
    chunk_text:str
    embedding:list[float]
    metadata:MetaData

token_splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=64)
DOC_NAME = 'Leave_Policy'

def create_embeddings(token_split_chunk:str, chunk_index:int)-> DocChunk:
    embedding = generate_embeddings(token_split_chunk)
    metadata = MetaData(chunk_index=chunk_index,
                        heading=cur_heading
                        )
    doc_chunk=DocChunk(id=f'{DOC_NAME}-{chunk_index}',
                    document_id=DOC_NAME,
                    chunk_text=token_split_chunk,
                    embedding=embedding,
                    metadata=metadata
                    )
    return doc_chunk.model_dump()

docs = Document('Leave_Policy.docx')
cur_chunk_text = ''
chunk_index=0
list_of_embedding_data = []
for doc in docs.paragraphs:
    if doc.style.name == 'Heading 1' and cur_chunk_text != '':
        token_split_chunks = token_splitter.split_text(cur_chunk_text)
        for token_split_chunk in token_split_chunks:
            chunk_index += 1
            doc_chunk = create_embeddings(token_split_chunk, chunk_index)
            cur_chunk_text = ''
            list_of_embedding_data.append(doc_chunk)

    if doc.style.name == 'Heading 1':
        cur_heading = doc.text
    cur_chunk_text += doc.text

token_split_chunks = token_splitter.split_text(cur_chunk_text)
for token_split_chunk in token_split_chunks:
    chunk_index += 1
    doc_chunk = create_embeddings(token_split_chunk, chunk_index)
    list_of_embedding_data.append(doc_chunk)

COSMOS_URL = os.environ['COSMOS_DB_CONNECTION_STRING']
client = CosmosClient(
    url=COSMOS_URL,
    credential=DefaultAzureCredential()
)
db = client.get_database_client("policy-embeddings")
container = db.get_container_client("embedding-data")
for embedding in list_of_embedding_data:
    container.create_item(body=embedding)



