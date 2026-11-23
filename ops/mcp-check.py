"""End-to-end check of the MCP server at its public address (MCP_PUBLIC_URL), as Claude uses it
after signing in: initialize, list the tools, call a read-only tool.

Run inside the mcp container on every deploy by ops/health-report.sh:
    docker compose exec -T mcp python - < ops/mcp-check.py
It gives itself a 5-minute access token straight in the database (only its hash, like a real
login), and deletes it when done. It prints status codes and counts only, never your data, since
the deploy log is public.
"""

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete

from app.db import engine
from app.mcp_server.oauth import SCOPE
from app.models import McpToken
from sqlalchemy.orm import Session

base = os.environ["MCP_PUBLIC_URL"].rstrip("/")
token = secrets.token_urlsafe(32)
grant = f"deploy-check-{secrets.token_hex(8)}"

with Session(engine) as session:
    session.add(
        McpToken(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            kind="access",
            grant_id=grant,
            client_id="deploy-check",
            scopes=SCOPE,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    session.commit()

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def rpc(client: httpx.Client, id_: int | None, method: str, params: dict | None = None):
    body = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        body["id"] = id_
    if params is not None:
        body["params"] = params
    return client.post(f"{base}/mcp", headers=headers, json=body)


ok = False
try:
    with httpx.Client(timeout=30) as client:
        r = rpc(
            client,
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "deploy-check", "version": "1"},
            },
        )
        name = r.json().get("result", {}).get("serverInfo", {}).get("name") if r.is_success else None
        print(f"mcp-check: initialize  http {r.status_code}  {r.elapsed.total_seconds():.2f}s  server={name}")
        r.raise_for_status()
        if sid := r.headers.get("mcp-session-id"):
            headers["mcp-session-id"] = sid
        headers["mcp-protocol-version"] = r.json()["result"]["protocolVersion"]
        rpc(client, None, "notifications/initialized")

        r = rpc(client, 2, "tools/list")
        tools = r.json().get("result", {}).get("tools", []) if r.is_success else []
        print(f"mcp-check: tools/list  http {r.status_code}  {r.elapsed.total_seconds():.2f}s  tools={len(tools)}")
        r.raise_for_status()

        r = rpc(client, 3, "tools/call", {"name": "get_cash_flow", "arguments": {}})
        result = r.json().get("result", {}) if r.is_success else {}
        print(
            f"mcp-check: get_cash_flow  http {r.status_code}  {r.elapsed.total_seconds():.2f}s"
            f"  error={result.get('isError')}  bytes={len(r.content)}"
        )
        ok = r.is_success and result.get("isError") is False
except Exception as error:  # report, never fail the deploy
    print(f"mcp-check: failed: {type(error).__name__}: {error}")
finally:
    with Session(engine) as session:
        session.execute(delete(McpToken).where(McpToken.grant_id == grant))
        session.commit()

print("mcp-check: OK, Claude's connector can use SmartFin" if ok else "mcp-check: NOT OK")
