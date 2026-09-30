"""Bank and card logins, managed from the web app.

The logins are kept by the scraper, encrypted in its own file; this router only passes requests
through to the scraper's API. Nothing here stores or logs a credential, and the scraper never
sends one back.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.labels import CARD_COMPANIES, institution_label

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections", tags=["connections"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
ConnectionId = Annotated[str, Path(pattern=r"^[\w-]{1,64}$")]
Credentials = Annotated[
    dict[Annotated[str, Field(max_length=40)], Annotated[str, Field(max_length=200)]],
    Field(max_length=10),
]


class Company(BaseModel):
    id: str
    label: str
    kind: Literal["bank", "card"]
    login_fields: list[str]


class LastSync(BaseModel):
    ok: bool
    error_type: str | None
    finished_at: str | None


class Connection(BaseModel):
    id: str
    company: str
    label: str
    kind: Literal["bank", "card"]
    # The end of the first login field, e.g. "•••789", to tell two logins apart
    hint: str | None
    added_at: str | None
    sync: Literal["running", "queued"] | None
    # How the latest sync since the scraper started went; None before the first
    last_sync: LastSync | None


class Connections(BaseModel):
    connections: list[Connection]
    companies: list[Company]


class ConnectionIn(BaseModel):
    company: str = Field(max_length=40)
    credentials: Credentials


class CredentialsIn(BaseModel):
    credentials: Credentials


def _kind(company: str) -> Literal["bank", "card"]:
    return "card" if company in CARD_COMPANIES else "bank"


def _connection(raw: dict[str, Any]) -> Connection:
    return Connection(
        **raw, label=institution_label(raw["company"]), kind=_kind(raw["company"])
    )


def call_scraper(settings: Settings, method: str, path: str, body: Any = None) -> Any:
    """One request to the scraper's API. Scraper errors come back as HTTPExceptions."""
    if not settings.ingest_token:
        raise HTTPException(503, "INGEST_TOKEN is not set")
    request = urllib.request.Request(
        settings.scraper_url.rstrip("/") + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {settings.ingest_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read()
    except urllib.error.HTTPError as err:
        try:
            detail = json.loads(err.read()).get("detail")
        except ValueError:
            detail = None
        if err.code in (404, 422):
            raise HTTPException(err.code, detail or "Rejected by the scraper") from None
        log.warning("Scraper API %s %s returned %s", method, path.split("/")[1], err.code)
        raise HTTPException(502, "The scraper returned an error") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        log.warning("Scraper API unreachable: %s", getattr(err, "reason", err))
        raise HTTPException(503, "The scraper is not reachable") from None
    return json.loads(payload) if payload else None


@router.get("")
def list_connections(settings: SettingsDep) -> Connections:
    companies = call_scraper(settings, "GET", "/companies")
    return Connections(
        connections=[_connection(c) for c in call_scraper(settings, "GET", "/accounts")],
        companies=sorted(
            (
                Company(
                    id=c["id"],
                    label=institution_label(c["id"]),
                    kind=_kind(c["id"]),
                    login_fields=c["login_fields"],
                )
                for c in companies
            ),
            key=lambda c: c.label,
        ),
    )


@router.post("", status_code=201)
def add_connection(body: ConnectionIn, settings: SettingsDep) -> Connection:
    """Save a new login with the scraper, which syncs it (a year back) right away."""
    return _connection(call_scraper(settings, "POST", "/accounts", body.model_dump()))


@router.put("/{connection_id}")
def update_connection(
    connection_id: ConnectionId, body: CredentialsIn, settings: SettingsDep
) -> Connection:
    """Replace a login's credentials (all of them: the old ones are never sent back)."""
    return _connection(
        call_scraper(settings, "PUT", f"/accounts/{connection_id}", body.model_dump())
    )


@router.delete("/{connection_id}", status_code=204)
def delete_connection(connection_id: ConnectionId, settings: SettingsDep) -> Response:
    call_scraper(settings, "DELETE", f"/accounts/{connection_id}")
    return Response(status_code=204)


@router.post("/sync", status_code=202)
def sync_all(settings: SettingsDep) -> list[Connection]:
    return [_connection(c) for c in call_scraper(settings, "POST", "/sync")]


@router.post("/{connection_id}/sync", status_code=202)
def sync_one(connection_id: ConnectionId, settings: SettingsDep) -> Connection:
    return _connection(call_scraper(settings, "POST", f"/accounts/{connection_id}/sync"))
