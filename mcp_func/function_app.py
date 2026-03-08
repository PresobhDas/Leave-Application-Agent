import azure.functions as func
from mcp_app import register_tools
from mcp.server.fastmcp import FastMCP

mcp_server = FastMCP('Leave-application-mcp-server')
register_tools(mcp_server)

asgi_app = mcp_server.streamable_http_app()
app = func.AsgiFunctionApp(
    app=asgi_app,
    http_auth_level=func.AuthLevel.FUNCTION
)
