from pathlib import Path
import sys
from contextlib import asynccontextmanager
import logging
import time
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Support running this file directly as well as importing app.main with Uvicorn.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routes import auth, chat, documents, quizzes, progress, media
from app.ai.tools import create_mcp_app, mcp_mount
from app.core.config import get_settings
from app.core.telemetry import event_logger

HOST = "127.0.0.1"
PORT = 8000
RELOAD = True

@asynccontextmanager
async def lifespan(app):
    mcp_server, mcp_app = create_mcp_app()
    mcp_mount.app = mcp_app
    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        mcp_mount.app = None


app = FastAPI(title="Study Mate API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().frontend_origins,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"],
                   expose_headers=["X-Request-ID", "X-Audio-Generated"])


class RequestMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        correlation_id = str(uuid4())
        started = time.perf_counter()
        status = 500
        async def measured_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                message = dict(message,headers=[*message.get('headers',[]),(b'x-request-id',correlation_id.encode())])
            await send(message)
        try:
            await self.app(scope,receive,measured_send)
        finally:
            event_logger('requests').info('request_completed',extra={'request_id':correlation_id,'method':scope['method'],'status':status,'latency_ms':round((time.perf_counter()-started)*1000,2)})


app.add_middleware(RequestMetricsMiddleware)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(quizzes.router)
app.include_router(progress.router)
app.include_router(media.router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
    # Validation errors must not echo submitted passwords back to clients.
    errors = [
        {key: value for key, value in error.items() if key not in {"input", "ctx"}}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to Study Mate API"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models")
def models(user=Depends(auth.get_current_user)):
    settings = get_settings()
    return {"providers": [
        {"id": "anthropic", "configured": bool(settings.anthropic_api_key), "model": settings.anthropic_model, "image_input": True},
        {"id": "openai", "configured": bool(settings.openai_api_key and settings.openai_model), "model": settings.openai_model, "image_input": False},
        {"id": "ollama", "configured": bool(settings.ollama_model), "model": settings.ollama_model, "image_input": False}],
        "voice_configured": bool(settings.openai_api_key), "note": "Configured is not a runtime availability guarantee. Local models must support structured output."}


# Mount last so API routes take precedence; the MCP app serves /mcp and auth metadata.
app.mount("/", mcp_mount)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        app_dir=str(Path(__file__).resolve().parent.parent),
    )
