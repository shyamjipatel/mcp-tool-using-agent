"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.storage.chat_store import ChatStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    store = ChatStore(os.getenv("DATABASE_PATH", "data/chat.db"))
    await store.initialize()
    app.state.chat_store = store
    yield


app = FastAPI(title="MCP Tool-Using Agent", version="0.1.0", lifespan=lifespan)
app.include_router(router)
WEB_DIR = Path(__file__).parent / "web"
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
