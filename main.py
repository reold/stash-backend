from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import PlainTextResponse

from routers import api

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

app.include_router(api.router)

@app.exception_handler(HTTPException)
def custom_http_exception(request, exc):
    return PlainTextResponse(exc.detail, exc.status_code)