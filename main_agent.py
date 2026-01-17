import requests
from pydantic import BaseModel

class InputDetails(BaseModel):
    inp_query:str

url = 'https://leave-policy-agent-aaavdzbuf3bcexej.westus2-01.azurewebsites.net/agent'
inp_details = InputDetails(inp_query='Hello How are you')
response = requests.post(url=url, json=inp_details.model_dump())

print(type(response))
print(response.json()['content'])