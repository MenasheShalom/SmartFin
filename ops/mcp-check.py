"""End-to-end check of the MCP server at its public address (MCP_PUBLIC_URL), as Claude uses it
after signing in: initialize, list the tools, call a read-only tool.

Run inside the mcp container on every deploy by ops/health-report.sh:
    docker compose exec -T mcp python - < ops/mcp-check.py
It gives itself a 5-minute access token straight in the database (only its hash, like a real
login), and deletes it when done. It prints status codes and counts only, never your data, since
the deploy log is public.
"""

import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.db import engine
from app.mcp_server.oauth import SCOPE
from app.models import McpToken
from sqlalchemy.orm import Session

# The address the MCP server uses: the tunnel's, when it follows one
try:
    from app.mcp_server.tunnel import tunnel_url
except ImportError:  # an image from before the server followed the tunnel
    tunnel_url = None
metrics = os.environ.get("MCP_TUNNEL_METRICS_URL", "")
followed = tunnel_url(metrics) if (tunnel_url and metrics) else None
base = (followed or os.environ["MCP_PUBLIC_URL"]).rstrip("/")
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
    "User-Agent": "SmartFin-deploy-check/1",
}


class Reply:
    def __init__(self, status: int, body: bytes, headers, seconds: float):
        self.status, self.content, self.headers, self.seconds = status, body, headers, seconds

    def json(self) -> dict:
        return json.loads(self.content) if self.content else {}


def rpc(id_: int | None, method: str, params: dict | None = None) -> Reply:
    body = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        body["id"] = id_
    if params is not None:
        body["params"] = params
    request = urllib.request.Request(
        f"{base}/mcp", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return Reply(response.status, response.read(), response.headers, time.monotonic() - start)
    except urllib.error.HTTPError as error:
        return Reply(error.code, error.read(), error.headers, time.monotonic() - start)


ok = False
try:
    r = rpc(
        1,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "deploy-check", "version": "1"},
        },
    )
    name = r.json().get("result", {}).get("serverInfo", {}).get("name") if r.status == 200 else None
    print(f"mcp-check: initialize  http {r.status}  {r.seconds:.2f}s  server={name}")
    if r.status == 200:
        if sid := r.headers.get("mcp-session-id"):
            headers["mcp-session-id"] = sid
        headers["mcp-protocol-version"] = r.json()["result"]["protocolVersion"]
        rpc(None, "notifications/initialized")

        r = rpc(2, "tools/list")
        tools = r.json().get("result", {}).get("tools", []) if r.status == 200 else []
        print(f"mcp-check: tools/list  http {r.status}  {r.seconds:.2f}s  tools={len(tools)}")

        r = rpc(3, "tools/call", {"name": "get_cash_flow", "arguments": {}})
        result = r.json().get("result", {}) if r.status == 200 else {}
        print(
            f"mcp-check: get_cash_flow  http {r.status}  {r.seconds:.2f}s"
            f"  error={result.get('isError')}  bytes={len(r.content)}"
        )
        ok = r.status == 200 and result.get("isError") is False and len(tools) > 0
except Exception as error:  # report, never fail the deploy
    print(f"mcp-check: failed: {type(error).__name__}: {error}")
finally:
    with Session(engine) as session:
        session.execute(delete(McpToken).where(McpToken.grant_id == grant))
        session.commit()

print("mcp-check: OK, Claude's connector can use SmartFin" if ok else "mcp-check: NOT OK")
