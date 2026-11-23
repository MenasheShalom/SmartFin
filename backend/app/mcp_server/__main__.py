"""python -m app.mcp_server: serve the MCP server on port 8001."""

import logging
import os

import uvicorn
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import engine
from app.mcp_server.server import build_app
from app.mcp_server.tunnel import announce, wait_for_tunnel_url, watch

log = logging.getLogger(__name__)

if __name__ == "__main__":
    settings = get_settings()
    # Behind the Cloudflare quick tunnel, its current address is the public one (MCP_PUBLIC_URL
    # from .env can be stale after a reboot); without it, MCP_PUBLIC_URL as set
    metrics = os.environ.get("MCP_TUNNEL_METRICS_URL", "")
    if metrics:
        url = wait_for_tunnel_url(metrics)
        if url:
            settings = settings.model_copy(update={"mcp_public_url": url})
            try:
                announce(sessionmaker(bind=engine, expire_on_commit=False), url)
            except Exception:
                log.exception("Couldn't raise the new-address alert")
        else:
            log.warning("The tunnel has no address; using MCP_PUBLIC_URL")
        watch(metrics, url or settings.mcp_public_url or "")

    uvicorn.run(
        build_app(engine, settings),
        host="0.0.0.0",
        port=int(os.environ.get("MCP_PORT", "8001")),
    )
