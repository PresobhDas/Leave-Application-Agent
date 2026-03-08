import requests
from pydantic import BaseModel

class InputDetails(BaseModel):
    inp_query:str

TENANT_ID = '74adb40f-d941-4a72-96c1-497a887069a0'
CLIENT_ID = '818def42-ceba-4b58-849c-532fa48d76ea'
CLIENT_SECRET = 'VKG8Q~YrDOIdqq1IRW.mgq~ryFMMb2xRo~faGbHx'
SCOPE = 'api://818def42-ceba-4b58-849c-532fa48d76ea/.default'
token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"

data = {
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scope": SCOPE,
}

token_resp = requests.post(url=token_url, data = data)
access_token = token_resp.json()['access_token']

headers = {
    'authorization' : f'Bearer {access_token}'
}

url = 'https://leave-policy-agent-aaavdzbuf3bcexej.westus2-01.azurewebsites.net/agent'
# leave-policy-agent-mcp-1-auczcxdxa7dwftd9.westus2-01.azurewebsites.net

inp_details = InputDetails(inp_query='what is the current temperature in the location of employee E1001?')
response = requests.post(url=url, headers=headers, json=inp_details.model_dump())

data = response.json()

for contents in data['messages']:
    print(contents['type'])
    print('-'*5)
    print(contents['content'])