import azure.functions as func
from mcp_app import register_tools
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp_server = FastMCP('Leave-application-mcp-server',
                     transport_security=TransportSecuritySettings(
                    # keep DNS rebinding protection on
                    enable_dns_rebinding_protection=True,
                    # allow the actual Azure host clients use
                    allowed_hosts=[
                        "leave-policy-agent-mcp-1-auczcxdxa7dwftd9.westus2-01.azurewebsites.net"
                        ],
                    ),
                )
register_tools(mcp_server)

asgi_app = mcp_server.streamable_http_app()

app = func.AsgiFunctionApp(
    app=asgi_app,
    http_auth_level=func.AuthLevel.ANONYMOUS
)
