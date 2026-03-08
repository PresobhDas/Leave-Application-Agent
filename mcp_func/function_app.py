import azure.functions as func
from mcp_app import register_tools
from mcp.server.fastmcp import FastMCP
from starlette.middleware.trustedhost import TrustedHostMiddleware

mcp_server = FastMCP('Leave-application-mcp-server')
register_tools(mcp_server)

asgi_app = mcp_server.streamable_http_app()
asgi_app = TrustedHostMiddleware(
    asgi_app,
    allowed_hosts=[
        "leave-policy-agent-mcp-1-auczcxdxa7dwftd9.westus2-01.azurewebsites.net",
        "localhost",
        "127.0.0.1"
    ]
)
app = func.AsgiFunctionApp(
    app=asgi_app,
    http_auth_level=func.AuthLevel.ANONYMOUS
)
