"""Follow the address of the Cloudflare quick tunnel (the mcp-tunnel service, ops/mcp-tunnel.sh).

A quick tunnel gets a new random address whenever it restarts (a reboot, say). The MCP server
signs Claude in under its public address, so it asks the tunnel for the address when it starts,
and exits when the address changes, so Docker restarts it with the new one. Each new address is
raised once as an alert (sent over Telegram/email when those are set up), since the Claude
connector then has to be added again with it.
"""

import json
import logging
import os
import threading
import time
import urllib.request

from sqlalchemy.orm import Session, sessionmaker

from app.alerts import raise_alert
from app.models import AlertType

log = logging.getLogger(__name__)

CHECK_EVERY = 60


def tunnel_url(metrics_url: str, timeout: float = 3) -> str | None:
    """https://<name>.trycloudflare.com from the tunnel's metrics server, or None."""
    try:
        with urllib.request.urlopen(f"{metrics_url.rstrip('/')}/quicktunnel", timeout=timeout) as r:
            host = json.load(r).get("hostname")
    except (OSError, ValueError):
        return None
    return f"https://{host}" if host else None


def wait_for_tunnel_url(metrics_url: str, seconds: float = 90) -> str | None:
    """The tunnel's address, waiting for it to come up (both start together after a reboot)."""
    deadline = time.monotonic() + seconds
    while True:
        url = tunnel_url(metrics_url)
        if url or time.monotonic() >= deadline:
            return url
        time.sleep(2)


def announce(sessions: sessionmaker[Session], url: str) -> bool:
    """Raise an alert for a new address, once per address. True if raised."""
    message = (
        "הכתובת שדרכה Claude מתחבר ל-SmartFin השתנתה. ב-claude.ai, בהגדרות › Connectors, "
        f"הסירו את המחבר SmartFin והוסיפו אותו שוב עם הכתובת:\n{url}/mcp"
    )
    with sessions() as session:
        alert = raise_alert(session, AlertType.MCP_ADDRESS, f"mcp_address:{url}", message)
        session.commit()
    return alert is not None


def watch(metrics_url: str, current: str, exit_=os._exit) -> threading.Thread:
    """In the background: exit the process when the tunnel's address stops being `current`."""

    def loop() -> None:
        while True:
            time.sleep(CHECK_EVERY)
            url = tunnel_url(metrics_url)
            if url and url != current:
                log.warning("The tunnel's address changed to %s; restarting to use it", url)
                exit_(3)
                return

    thread = threading.Thread(target=loop, name="tunnel-watch", daemon=True)
    thread.start()
    return thread
