import azure.functions as func
from mcp_app import mcp_server
from azure.functions import AsgiMiddleware

# app = func.AsgiFunctionApp(
#     app=mcp_server,
#     http_auth_level=func.AuthLevel.ANONYMOUS,  # or func.AuthLevel.FUNCTION
# )

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(
    route="{*route}",  # <-- catch-all so /mcp is forwarded
    methods=["GET", "POST", "DELETE", "OPTIONS"],  # <-- IMPORTANT
    auth_level=func.AuthLevel.ANONYMOUS
)
def http_app_func(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    return AsgiMiddleware(mcp_server).handle(req, context)