import requests
from pydantic import BaseModel

class InputDetails(BaseModel):
    inp_query:str

url = 'https://leave-agent-api.ashyglacier-369787e5.westus2.azurecontainerapps.io/evaluate'
# leave-policy-agent-mcp-1-auczcxdxa7dwftd9.westus2-01.azurewebsites.net

# inp_details = InputDetails(inp_query='What is the name of employee E1003?')
# response = requests.post(url=url, json=inp_details.model_dump())
response = requests.post(url=url)
# response = requests.get(url=url, timeout=20)


data = response.json()
print(data)

# for contents in data['messages']:
#     print(contents['type'])
#     print('-'*5)
#     print(contents['content'])