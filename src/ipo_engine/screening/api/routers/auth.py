"""
Sign-in, sign-out, browser sessions and invitations.

Google sign-in is optional: with no GOOGLE_CLIENT_ID these routes report that it is off. A session
is an HttpOnly cookie; the web app reads the CSRF token from ``GET /auth/csrf`` and sends it in
``X-CSRF-Token`` on every change. Personal API tokens (``Authorization: Bearer``) need neither.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ipo_engine.screening.api.dependencies import Container, get_container
from ipo_engine.screening.core.security import (
    SESSION_COOKIE,
    Principal,
    Role,
    get_principal,
    require_role,
)
from ipo_engine.screening.services.accounts import AccountError

router = APIRouter(prefix="/api/v1", tags=["auth"])
admin = require_role(Role.ADMIN)
STATE_COOKIE = "ipo_oauth_state"


def _need_accounts(c: Container) -> None:
    if not c.settings.accounts_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Accounts are not enabled.")


def _session_only(p: Principal) -> str:
    if p.auth != "session" or p.session_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Sign in with a browser session.")
    return p.session_id


def _back(c: Container, path: str, **query: str) -> str:
    base = c.settings.public_base_url.rstrip("/")
    return base + path + ("?" + urllib.parse.urlencode(query) if query else "")


@router.get("/auth/providers")
def providers(c: Container = Depends(get_container)) -> dict[str, Any]:
    return {
        "accounts": c.settings.accounts_enabled,
        "google": c.signin.available,
        "signup": c.settings.signup_mode,
    }


@router.get("/auth/login/google")
def login_google(
    next_url: str | None = Query(default=None, alias="next", max_length=500),
    invitation: str | None = Query(default=None, max_length=200),
    c: Container = Depends(get_container),
) -> Response:
    _need_accounts(c)
    try:
        url, state = c.signin.begin(next_url=next_url, invitation_token=invitation)
    except AccountError as exc:
        return RedirectResponse(_back(c, "/login", error=exc.message), status_code=303)
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax",
        secure=c.settings.cookie_secure, path="/api/v1/auth",
    )  # fmt: skip
    return response


@router.get("/auth/callback/google")
def callback_google(
    request: Request,
    code: str | None = Query(default=None, max_length=2000),
    state: str | None = Query(default=None, max_length=200),
    error: str | None = Query(default=None, max_length=200),
    c: Container = Depends(get_container),
) -> Response:
    _need_accounts(c)
    if error or not code or not state:
        return RedirectResponse(_back(c, "/login", error="Sign-in was cancelled."), status_code=303)
    try:
        token, _csrf, next_url = c.signin.complete(
            code=code,
            state=state,
            bound_state=request.cookies.get(STATE_COOKIE),
            user_agent=request.headers.get("user-agent"),
        )
    except AccountError as exc:
        resp = RedirectResponse(_back(c, "/login", error=exc.message), status_code=303)
        resp.delete_cookie(STATE_COOKIE, path="/api/v1/auth")
        return resp
    resp = RedirectResponse(_back(c, next_url), status_code=303)
    resp.delete_cookie(STATE_COOKIE, path="/api/v1/auth")
    resp.set_cookie(
        SESSION_COOKIE, token, max_age=c.settings.session_days * 86400, httponly=True,
        samesite="lax", secure=c.settings.cookie_secure, path="/",
    )  # fmt: skip
    return resp


@router.get("/auth/csrf")
def csrf(request: Request, p: Principal = Depends(get_principal)) -> dict[str, str]:
    _session_only(p)
    return {"csrf_token": request.state.csrf_token}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Response:
    c.sessions.revoke_by_id(_session_only(p), actor=p.user_id)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.get("/auth/sessions")
def list_sessions(
    c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Any:
    _need_accounts(c)
    return c.sessions.list(p.user_id, current=p.session_id)


@router.delete("/auth/sessions/{session_ref}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_ref: str, c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Response:
    _need_accounts(c)
    c.sessions.revoke(p.user_id, session_ref, actor=p.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/sessions/revoke-others")
def revoke_other_sessions(
    c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> dict[str, int]:
    _need_accounts(c)
    return {"revoked": c.sessions.revoke_all(p.user_id, except_id=p.session_id)}


class SwitchOrg(BaseModel):
    org_id: str = Field(min_length=1, max_length=36)


@router.post("/auth/switch-org")
def switch_org(
    body: SwitchOrg, c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> dict[str, str]:
    c.sessions.switch_org(_session_only(p), p.user_id, body.org_id)
    return {"org_id": body.org_id}


@router.get("/auth/organisations")
def my_organisations(
    c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Any:
    _need_accounts(c)
    return c.accounts.organisations_of(p.user_id)


# ------------------------------------------------------------------ invitations
class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role = Role.VIEWER


@router.post("/org/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(
    body: InvitationCreate, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    """The link is in this response only. Send it to the person (e-mail delivery is optional)."""
    _need_accounts(c)
    made = c.accounts.invite(
        p.org_id, body.email, body.role, actor=p.user_id, days=c.settings.invitation_days
    )
    link = _back(c, "/invite", token=made["token"])
    return {**made, "link": link}


@router.get("/org/invitations")
def list_invitations(c: Container = Depends(get_container), p: Principal = Depends(admin)) -> Any:
    _need_accounts(c)
    return c.accounts.invitations(p.org_id)


@router.delete("/org/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: str, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Response:
    _need_accounts(c)
    c.accounts.revoke_invitation(p.org_id, invitation_id, actor=p.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/invitation")
def invitation_preview(
    token: str = Query(min_length=10, max_length=200), c: Container = Depends(get_container)
) -> Any:
    """What an invitation link is for, so the page can say 'Join X as reviewer' before sign-in."""
    _need_accounts(c)
    found = c.accounts.invitation_preview(token)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invitation not found or expired.")
    return found
