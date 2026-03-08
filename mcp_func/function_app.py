# import azure.functions as func
# from mcp_app import register_tools
# from mcp.server.fastmcp import FastMCP

# mcp_server = FastMCP('Leave-application-mcp-server')
# register_tools(mcp_server)

# asgi_app = mcp_server.streamable_http_app()
# app = func.AsgiFunctionApp(
#     app=asgi_app,
#     http_auth_level=func.AuthLevel.FUNCTION
# )

import azure.functions as func
from fastapi import FastAPI
import sys
import os
import traceback

diagnostic_app = FastAPI()

@diagnostic_app.get("/health")
async def health():
    results = {}

    # Test each import individually
    for module in ["mcp", "fastmcp", "mcp.server.fastmcp"]:
        try:
            __import__(module)
            results[module] = "OK"
        except Exception as e:
            results[module] = f"FAILED: {str(e)}"

    # Test your specific import
    try:
        from mcp_app import register_tools
        results["register_tools"] = "OK"
    except Exception as e:
        results["register_tools"] = f"FAILED: {traceback.format_exc()}"

    return {
        "python_version": sys.version,
        "files": os.listdir("/home/site/wwwroot"),
        "imports": results
    }

app = func.AsgiFunctionApp(
    app=diagnostic_app,
    http_auth_level=func.AuthLevel.ANONYMOUS
)