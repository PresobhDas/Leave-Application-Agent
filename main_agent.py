import requests
from pydantic import BaseModel

class InputDetails(BaseModel):
    inp_query:str

url = 'https://leave-policy-agent-aaavdzbuf3bcexej.westus2-01.azurewebsites.net/agent'
inp_details = InputDetails(inp_query='If the current temperature of the work location of employee E1001 is above freezing, then pull the leave records for that employee')
response = requests.post(url=url, json=inp_details.model_dump())
# print(response)

data = response.json()

for contents in data['messages']:
    print(contents['type'])
    print('-'*5)
    print(contents['content'])
    print('\n')