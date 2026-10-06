"""python -m app.mcp_server: serve the MCP server on port 8001."""

import os

import uvicorn

from app.config import get_settings
from app.db import engine
from app.mcp_server.server import build_app

if __name__ == "__main__":
    uvicorn.run(
        build_app(engine, get_settings()),
        host="0.0.0.0",
        port=int(os.environ.get("MCP_PORT", "8001")),
    )
