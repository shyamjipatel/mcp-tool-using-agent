"""FastAPI application entry point."""

import logging
import os

from fastapi import FastAPI

from app.api.routes import router

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(message)s")

app = FastAPI(title="MCP Tool-Using Agent", version="0.1.0")
app.include_router(router)
