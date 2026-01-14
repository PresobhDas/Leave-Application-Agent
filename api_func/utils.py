import os
from langchain_openai import ChatOpenAI

def get_chat_model() -> ChatOpenAI:
    chat_model = ChatOpenAI(
        name='gpt-4o-mini',
        api_key=os.environ['OPENAI_API_KEY']
    )

    return chat_model