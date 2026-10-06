"""OAuth for the MCP server, so only the SmartFin login can connect Claude.

Claude registers itself (dynamic client registration), then sends you to /login, where you sign
in with your SmartFin username and password. Only Claude's own callback addresses
(MCP_REDIRECT_URIS) can receive the result, so another app can't use a login to get at the data.

Registrations and tokens live in the database (only hashes of the tokens); a pending login and
the short-lived code that follows it are kept in memory.
"""

import html
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import anyio.to_thread
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.auth import LoginThrottle, check_login, token_hash
from app.models import McpClient, McpToken

SCOPE = "smartfin:read"
ACCESS_SECONDS = 60 * 60
REFRESH_DAYS = 90
CODE_SECONDS = 5 * 60
# Time to type the username and password
LOGIN_SECONDS = 10 * 60
MAX_PENDING_LOGINS = 100
# Anyone can register; registrations that never logged in are dropped after this
UNUSED_CLIENT_DAYS = 1


@dataclass
class PendingLogin:
    client_id: str
    params: AuthorizationParams
    expires_at: float


class SmartFinOAuthProvider:
    def __init__(
        self, sessions: sessionmaker[Session], public_url: str, redirect_uris: list[str]
    ) -> None:
        self.sessions = sessions
        self.public_url = public_url.rstrip("/")
        self.resource = f"{self.public_url}/mcp"
        self.redirect_uris = set(redirect_uris)
        self.pending: dict[str, PendingLogin] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.throttle = LoginThrottle()

    # --- Registration ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self.sessions() as session:
            client = session.get(McpClient, client_id)
            return OAuthClientInformationFull.model_validate_json(client.info) if client else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = {str(uri) for uri in client_info.redirect_uris or []}
        if not uris or not uris <= self.redirect_uris:
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="Only Claude can connect to this server",
            )
        now = datetime.now(UTC)
        with self.sessions() as session:
            session.execute(
                delete(McpClient).where(
                    McpClient.created_at < now - timedelta(days=UNUSED_CLIENT_DAYS),
                    McpClient.client_id.not_in(select(McpToken.client_id)),
                )
            )
            session.add(
                McpClient(
                    client_id=client_info.client_id,
                    info=client_info.model_dump_json(),
                    created_at=now,
                )
            )
            session.commit()

    # --- Login ---

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if str(params.redirect_uri) not in self.redirect_uris:
            raise AuthorizeError(error="invalid_request", error_description="Unknown redirect_uri")
        if params.resource and params.resource.rstrip("/") != self.resource:
            raise AuthorizeError(
                error="invalid_request", error_description=f"This server only grants {self.resource}"
            )
        if params.scopes and set(params.scopes) - {SCOPE}:
            raise AuthorizeError(error="invalid_scope", error_description=f"Only {SCOPE} exists")
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v.expires_at > now}
        if len(self.pending) >= MAX_PENDING_LOGINS:
            del self.pending[next(iter(self.pending))]
        request_id = secrets.token_urlsafe(32)
        self.pending[request_id] = PendingLogin(client.client_id, params, now + LOGIN_SECONDS)
        return f"{self.public_url}/login?request={request_id}"

    async def login_page(self, request: Request) -> Response:
        if request.method == "GET":
            request_id = request.query_params.get("request", "")
            if not self._pending(request_id):
                return _expired()
            return _form(request_id)

        form = await request.form()
        request_id = str(form.get("request", ""))
        pending = self._pending(request_id)
        if pending is None:
            return _expired()
        # One key for everyone: behind a tunnel every visitor has the tunnel's address, and the
        # forwarded headers that would tell them apart can be faked
        key = "login"
        wait = self.throttle.wait_seconds(key)
        if wait:
            return _form(request_id, f"יותר מדי ניסיונות. נסו שוב בעוד {wait} שניות.", 429)
        username, password = str(form.get("username", ""))[:64], str(form.get("password", ""))[:256]
        if not await anyio.to_thread.run_sync(self._check_login, username, password):
            self.throttle.failed(key)
            return _form(request_id, "שם המשתמש או הסיסמה שגויים.", 401)
        self.throttle.succeeded(key)

        # A second submit of the same form, e.g. a double tap, finds it already used
        if self.pending.pop(request_id, None) is None:
            return _expired()
        now = time.time()
        self.codes = {k: v for k, v in self.codes.items() if v.expires_at > now}
        code = secrets.token_urlsafe(32)
        params = pending.params
        self.codes[code] = AuthorizationCode(
            code=code,
            scopes=[SCOPE],
            expires_at=now + CODE_SECONDS,
            client_id=pending.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self.resource,
        )
        target = construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)
        return RedirectResponse(target, status_code=302)

    def _pending(self, request_id: str) -> PendingLogin | None:
        pending = self.pending.get(request_id)
        return pending if pending and pending.expires_at > time.time() else None

    def _check_login(self, username: str, password: str) -> bool:
        with self.sessions() as session:
            return check_login(session, username, password) is not None

    # --- Tokens ---

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self.codes.get(authorization_code)
        return code if code and code.client_id == client.client_id else None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # One use only
        self.codes.pop(authorization_code.code, None)
        return self._issue(client.client_id, secrets.token_urlsafe(16))

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = self._find(refresh_token, "refresh")
        if row is None or row.client_id != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row.client_id,
            scopes=row.scopes.split(),
            expires_at=int(row.expires_at.timestamp()),
            resource=self.resource,
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        row = self._find(refresh_token.token, "refresh")
        if row is None:
            raise TokenError(error="invalid_grant", error_description="Refresh token was revoked")
        # Rotate: the old access and refresh tokens stop working
        return self._issue(client.client_id, row.grant_id)

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self._find(token, "access")
        if row is None:
            return None
        return AccessToken(
            token=token,
            client_id=row.client_id,
            scopes=row.scopes.split(),
            expires_at=int(row.expires_at.timestamp()),
            resource=self.resource,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self.sessions() as session:
            grant_id = session.scalar(
                select(McpToken.grant_id).where(McpToken.token_hash == token_hash(token.token))
            )
            if grant_id:
                session.execute(delete(McpToken).where(McpToken.grant_id == grant_id))
                session.commit()

    def _find(self, token: str, kind: str) -> McpToken | None:
        with self.sessions() as session:
            return session.scalars(
                select(McpToken).where(
                    McpToken.token_hash == token_hash(token),
                    McpToken.kind == kind,
                    McpToken.expires_at > datetime.now(UTC),
                )
            ).one_or_none()

    def _issue(self, client_id: str, grant_id: str) -> OAuthToken:
        """A new access and refresh token for the grant, replacing any it had."""
        now = datetime.now(UTC)
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.sessions() as session:
            session.execute(
                delete(McpToken).where(
                    (McpToken.grant_id == grant_id) | (McpToken.expires_at < now)
                )
            )
            for token, kind, expires in (
                (access, "access", now + timedelta(seconds=ACCESS_SECONDS)),
                (refresh, "refresh", now + timedelta(days=REFRESH_DAYS)),
            ):
                session.add(
                    McpToken(
                        token_hash=token_hash(token),
                        kind=kind,
                        grant_id=grant_id,
                        client_id=client_id,
                        scopes=SCOPE,
                        expires_at=expires,
                    )
                )
            session.commit()
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_SECONDS,
            refresh_token=refresh,
            scope=SCOPE,
        )


# --- The login page ---

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}

_STYLE = """
:root { color-scheme: light dark; --bg: #f6f7f9; --card: #fff; --text: #1d2330; --muted: #5d6675;
  --line: #d5d9e0; --accent: #2457c5; --error: #b3261e; }
@media (prefers-color-scheme: dark) { :root { --bg: #12151b; --card: #1c2029; --text: #e7eaf0;
  --muted: #a3abb9; --line: #343a47; --accent: #7aa2ff; --error: #ff8a80; } }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px;
  background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, sans-serif; }
main { width: 100%; max-width: 360px; background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; padding: 24px; }
h1 { font-size: 1.25rem; margin: 0 0 8px; }
p { margin: 0 0 16px; color: var(--muted); }
label { display: block; margin: 12px 0 4px; font-weight: 600; }
input { width: 100%; padding: 10px 12px; font: inherit; color: inherit; background: transparent;
  border: 1px solid var(--line); border-radius: 8px; }
button { width: 100%; margin-top: 20px; padding: 12px; font: inherit; font-weight: 600;
  color: #fff; background: var(--accent); border: 0; border-radius: 8px; cursor: pointer; }
.error { color: var(--error); margin: 12px 0 0; }
"""


def _page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f'<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>SmartFin · חיבור Claude</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>",
        status_code=status,
        headers=_SECURITY_HEADERS,
    )


def _form(request_id: str, error: str | None = None, status: int = 200) -> HTMLResponse:
    error_html = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    return _page(
        "<h1>חיבור Claude ל-SmartFin</h1>"
        "<p>Claude מבקש לקרוא את נתוני SmartFin: תזרים, תנועות, תקציבים והיסטוריה. "
        "הוא לא יוכל לשנות דבר.</p>"
        '<form method="post" action="login">'
        f'<input type="hidden" name="request" value="{html.escape(request_id)}">'
        '<label for="username">שם משתמש</label>'
        '<input id="username" name="username" autocomplete="username" required autofocus>'
        '<label for="password">סיסמה</label>'
        '<input id="password" name="password" type="password" '
        'autocomplete="current-password" required>'
        f"{error_html}"
        '<button type="submit">התחברות</button>'
        "</form>",
        status,
    )


def _expired() -> HTMLResponse:
    return _page(
        "<h1>הקישור פג תוקף</h1><p>חזרו ל-Claude והתחילו את החיבור מחדש.</p>", status=400
    )
