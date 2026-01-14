from fastmcp import FastMCP

mcp_api_app = FastMCP()

@mcp_api_app.tool()
async def get_weather(city:str) -> dict:
    return {'city' : city,
            'weather' : 'cool'}

mcp_server = mcp_api_app.streamable_http_app()