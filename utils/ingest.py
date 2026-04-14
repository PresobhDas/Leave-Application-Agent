from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
import re
from langchain_core.documents import Document

def get_chunks(file_path:Path) -> Document:
    loader = PyPDFLoader(file_path=file_path)
    file_data = loader.load()
    full_text = ''
    for doc in file_data:
        full_text += doc.page_content

    pattern = r'(?m)^[•]?\s*(\d+(?:\.\d+)+)\s+([^\n]+)'
    matches = list(re.finditer(pattern, full_text))

    langchain_doc = []

    for i, match in enumerate(matches):
        section_id = match.group(1)
        title = match.group(2).strip()

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)

        content = full_text[start:end].strip()
        if content:
            page_content = f'{section_id} {title}\n{content}'
            metadata = {
                'Section_id' : section_id,
                'title' : title
            }
            langchain_doc.append(
                Document(page_content=page_content, metadata=metadata)
            )

    return langchain_doc

def read_files():
    folder = Path('./Docs')
    for files in folder.iterdir():
        if files.is_file():
            langchain_document = get_chunks(files)

read_files()