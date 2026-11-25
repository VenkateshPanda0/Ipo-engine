"""
Accounts API: the caller's organisation, its members, and the caller's personal tokens.

No route takes an organisation id: every route acts on the organisation of the authenticated caller,
so there is nothing to forge. (Cases and reports are scoped in ``v1.py``; this router has its own
tests because it has no case ids to scope.)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ipo_engine.screening.api.dependencies import Container, get_container
from ipo_engine.screening.core.security import Principal, Role, get_principal, require_role
from ipo_engine.screening.services.accounts import AccountError

router = APIRouter(prefix="/api/v1", tags=["accounts"])
admin = require_role(Role.ADMIN)
reviewer = require_role(Role.REVIEWER)


def _need_accounts(c: Container) -> None:
    if not c.settings.accounts_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Accounts are not enabled.")


def _need_user(c: Container, p: Principal) -> None:
    """Tokens and memberships belong to database users, not to the configured API keys."""
    try:
        c.accounts.get_user(p.user_id)
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Sign in as a user to do this."
        ) from None


class OrgPatch(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role = Role.VIEWER


class MemberPatch(BaseModel):
    role: Role


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Role | None = None
    days: int | None = Field(default=90, ge=1, le=3650)


@router.get("/org")
def get_org(c: Container = Depends(get_container), p: Principal = Depends(get_principal)) -> Any:
    _need_accounts(c)
    return {**c.accounts.get_org(p.org_id), "role": p.role.value}


@router.patch("/org")
def rename_org(
    body: OrgPatch, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    _need_accounts(c)
    return c.accounts.rename_org(p.org_id, body.name, actor=p.user_id)


@router.get("/org/members")
def list_members(c: Container = Depends(get_container), p: Principal = Depends(reviewer)) -> Any:
    _need_accounts(c)
    return c.accounts.members(p.org_id)


@router.post("/org/members", status_code=status.HTTP_201_CREATED)
def add_member(
    body: MemberAdd, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    """Add an existing or new person by email (sign-in links come with invitations)."""
    _need_accounts(c)
    user = c.accounts.get_or_create_user(body.email)
    return c.accounts.add_member(p.org_id, user["id"], body.role, actor=p.user_id)


@router.patch("/org/members/{user_id}")
def change_role(
    user_id: str,
    body: MemberPatch,
    c: Container = Depends(get_container),
    p: Principal = Depends(admin),
) -> Any:
    _need_accounts(c)
    if c.accounts.role_of(p.org_id, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such member.")
    if user_id == p.user_id and body.role != Role.ADMIN:
        raise AccountError("You cannot lower your own role; ask another admin.")
    return c.accounts.add_member(p.org_id, user_id, body.role, actor=p.user_id)


@router.delete("/org/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: str, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Response:
    _need_accounts(c)
    c.accounts.remove_member(p.org_id, user_id, actor=p.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tokens")
def list_tokens(
    c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Any:
    _need_accounts(c)
    _need_user(c, p)
    return c.accounts.list_tokens(p.user_id, p.org_id)


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
def create_token(
    body: TokenCreate, c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Any:
    """The token is in this response only; it cannot be shown again."""
    _need_accounts(c)
    _need_user(c, p)
    return c.accounts.create_token(
        org_id=p.org_id, user_id=p.user_id, name=body.name, role=body.role, days=body.days
    )


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: str, c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Response:
    _need_accounts(c)
    _need_user(c, p)
    c.accounts.revoke_token(token_id, user_id=p.user_id, org_id=p.org_id, actor=p.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
