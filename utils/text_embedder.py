from sentence_transformers import SentenceTransformer
from docx import Document
from langchain_text_splitters import TokenTextSplitter
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient

# token_splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=64)

# docs = Document('Leave_Policy.docx')
# doc_chunks = []
# cur_chunk_text = ''
# for doc in docs.paragraphs:
#     if doc.style.name == 'Heading 1':
#         token_split_chunks = token_splitter.split_text(cur_chunk_text)
#         doc_chunks.extend(token_split_chunks)
#         cur_chunk_text = ''
#     cur_chunk_text += doc.text

# token_split_chunks = token_splitter.split_text(cur_chunk_text)
# doc_chunks.extend(token_split_chunks)

# model = SentenceTransformer('BAAI/bge-base-en-v1.5')
# embeddings = model.encode(doc_chunks, normalize_embeddings=False)

# COSMOS_URL = 'https://azure-data-storage.documents.azure.com:443/'

# client = CosmosClient(
#     url=COSMOS_URL,
#     credential=DefaultAzureCredential()
# )

# db = client.get_database_client("leave-db")
# container = db.get_container_client("employee-leaves")

from azure.identity import DefaultAzureCredential

cred = DefaultAzureCredential()
token = cred.get_token("https://management.azure.com/.default")
print("Token acquired!")