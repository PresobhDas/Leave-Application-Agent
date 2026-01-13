import azure.functions as func
from src.api_app import api_server


app = func.AsgiFunctionApp(
    app=api_server,
    http_auth_level=func.AuthLevel.ANONYMOUS,  # or func.AuthLevel.FUNCTION
)