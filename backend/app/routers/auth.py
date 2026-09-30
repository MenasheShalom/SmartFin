from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete

from app.auth import (
    COOKIE_NAME,
    MIN_PASSWORD,
    check_login,
    create_session,
    create_user,
    end_sessions,
    get_user,
    require_user,
    set_credentials,
    throttle,
    token_hash,
    verify_password,
)
from app.config import Settings, get_settings
from app.models import UserSession
from app.routers.common import SessionDep

router = APIRouter(prefix="/api/auth", tags=["auth"])

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Password = Annotated[str, Field(min_length=MIN_PASSWORD, max_length=256)]


class Credentials(BaseModel):
    username: Username
    password: Password


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class AccountIn(BaseModel):
    current_password: str = Field(max_length=256)
    username: Username
    # Leave out to keep the current password
    new_password: Password | None = None


class Status(BaseModel):
    # True until the first user signs up in the web app
    setup_required: bool


class Me(BaseModel):
    authenticated: bool
    username: str | None = None


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _start_session(session: SessionDep, response: Response, settings: Settings) -> None:
    token, expires = create_session(session)
    response.set_cookie(
        COOKIE_NAME,
        token,
        expires=expires,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.get("/status")
def status(session: SessionDep) -> Status:
    return Status(setup_required=get_user(session) is None)


@router.post("/setup", status_code=201)
def setup(
    body: Credentials,
    response: Response,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Me:
    """First start: create the one login and log in with it."""
    user = create_user(session, body.username, body.password)
    if user is None:
        raise HTTPException(409, "Already set up")
    _start_session(session, response, settings)
    return Me(authenticated=True, username=user.username)


@router.post("/login")
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Me:
    if get_user(session) is None:
        raise HTTPException(503, "Not set up yet")
    key = _client_key(request)
    wait = throttle.wait_seconds(key)
    if wait:
        raise HTTPException(429, "Too many attempts", headers={"Retry-After": str(wait)})
    user = check_login(session, body.username, body.password)
    if user is None:
        throttle.failed(key)
        raise HTTPException(401, "Wrong username or password")
    throttle.succeeded(key)
    _start_session(session, response, settings)
    return Me(authenticated=True, username=user.username)


@router.post("/logout", dependencies=[Depends(require_user)])
def logout(request: Request, response: Response, session: SessionDep) -> Me:
    token = request.cookies.get(COOKIE_NAME, "")
    session.execute(delete(UserSession).where(UserSession.token_hash == token_hash(token)))
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return Me(authenticated=False)


@router.get("/me", dependencies=[Depends(require_user)])
def me(session: SessionDep) -> Me:
    user = get_user(session)
    return Me(authenticated=True, username=user.username if user else None)


@router.put("/account", dependencies=[Depends(require_user)])
def update_account(body: AccountIn, request: Request, session: SessionDep) -> Me:
    """Change the username and/or password. Other browsers are logged out."""
    user = get_user(session)
    key = _client_key(request)
    wait = throttle.wait_seconds(key)
    if wait:
        raise HTTPException(429, "Too many attempts", headers={"Retry-After": str(wait)})
    # Not 401: that would read as "logged out" to the web app
    if user is None or not verify_password(body.current_password, user.password_hash):
        throttle.failed(key)
        raise HTTPException(400, "Current password is wrong")
    throttle.succeeded(key)
    user = set_credentials(session, body.username, body.new_password)
    end_sessions(session, keep_token=request.cookies.get(COOKIE_NAME))
    return Me(authenticated=True, username=user.username)
