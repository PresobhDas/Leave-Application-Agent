import azure.functions as func
from mcp_app import register_tools

mcp_api_app = func.FunctionApp()
register_tools(mcp_api_app)
