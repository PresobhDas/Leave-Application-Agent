import azure.functions as func
from mcp_app import mcp_server

app = func.AsgiFunctionApp(
    app=mcp_server,
    http_auth_level=func.AuthLevel.ANONYMOUS,  # or func.AuthLevel.FUNCTION
)