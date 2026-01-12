import azure.functions as func
from azure.functions import AsgiMiddleware


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("pong", status_code=200)

@app.route(route="{*path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def main(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    from src.api_app import api_server
    return AsgiMiddleware(api_server).handle(req, context)