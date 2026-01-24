import requests
from pydantic import BaseModel

class InputDetails(BaseModel):
    inp_query:str

url = 'https://leave-policy-agent-aaavdzbuf3bcexej.westus2-01.azurewebsites.net/agent'
inp_details = InputDetails(inp_query='Get me the employee records of employee ID E1002')
response = requests.post(url=url, json=inp_details.model_dump())

data = response.json()

for contents in data['messages']:
    print(contents['type'])
    print('-'*5)
    print(contents['content'])
    print('\n')