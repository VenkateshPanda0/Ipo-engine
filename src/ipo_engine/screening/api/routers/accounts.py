"""
Accounts API: the caller's organisation, its members, and the caller's personal tokens.

No route takes an organisation id: every route acts on the organisation of the authenticated caller,
so there is nothing to forge. (Cases and reports are scoped in ``v1.py``; this router has its own
tests because it has no case ids to scope.)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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


@router.get("/org/export")
def export_org(
    include_files: bool = False,
    c: Container = Depends(get_container),
    p: Principal = Depends(admin),
) -> Response:
    """Everything the organisation holds, as a zip of JSON files (and the PDFs if asked)."""
    _need_accounts(c)
    data = c.lifecycle.export_org(p.org_id, actor=p.user_id, include_files=include_files)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="organisation-export.zip"'},
    )


@router.delete("/org", status_code=status.HTTP_204_NO_CONTENT)
def delete_org(
    confirm: str = Query(min_length=1, max_length=200),
    c: Container = Depends(get_container),
    p: Principal = Depends(admin),
) -> Response:
    """Switch the organisation off. Pass its exact name as ``confirm``."""
    _need_accounts(c)
    if not c.accounts.is_owner(p.org_id, p.user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only an owner can delete it.")
    c.lifecycle.delete_org(p.org_id, actor=p.user_id, confirm=confirm)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/export")
def export_me(c: Container = Depends(get_container), p: Principal = Depends(get_principal)) -> Any:
    """What the service holds about the signed-in person."""
    _need_accounts(c)
    _need_user(c, p)
    return c.lifecycle.export_user(p.user_id)


class SettingsPatch(BaseModel):
    four_eyes: bool | None = None
    webhooks_enabled: bool | None = None


@router.get("/org/settings")
def get_settings_(
    c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Any:
    _need_accounts(c)
    return c.collab.settings(p.org_id)


@router.patch("/org/settings")
def patch_settings(
    body: SettingsPatch, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    _need_accounts(c)
    changes = body.model_dump(exclude_none=True)
    return c.collab.update_settings(p.org_id, changes, actor=p.user_id)


@router.get("/org/usage")
def org_usage(
    days: int = Query(default=30, ge=1, le=366),
    c: Container = Depends(get_container),
    p: Principal = Depends(admin),
) -> Any:
    _need_accounts(c)
    return c.collab.usage(p.org_id, days=days)


@router.get("/onboarding")
def onboarding(c: Container = Depends(get_container), p: Principal = Depends(get_principal)) -> Any:
    _need_accounts(c)
    return c.collab.onboarding(p.org_id, p.user_id)


@router.get("/notifications")
def notifications(
    unread: bool = False,
    c: Container = Depends(get_container),
    p: Principal = Depends(get_principal),
) -> Any:
    _need_accounts(c)
    _need_user(c, p)
    return c.collab.notifications(p.user_id, p.org_id, unread_only=unread)


@router.post("/notifications/read")
def read_all_notifications(
    c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Any:
    _need_accounts(c)
    _need_user(c, p)
    return {"marked": c.collab.mark_read(p.user_id, p.org_id, None)}


@router.post("/notifications/{notification_id}/read")
def read_notification(
    notification_id: str,
    c: Container = Depends(get_container),
    p: Principal = Depends(get_principal),
) -> Any:
    _need_accounts(c)
    _need_user(c, p)
    return {"marked": c.collab.mark_read(p.user_id, p.org_id, notification_id)}


class SavedFilterBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: str = "cases"
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/saved-filters")
def list_saved(c: Container = Depends(get_container), p: Principal = Depends(get_principal)) -> Any:
    _need_accounts(c)
    _need_user(c, p)
    return c.collab.saved_filters(p.user_id, p.org_id)


@router.post("/saved-filters", status_code=status.HTTP_201_CREATED)
def save_filter(
    body: SavedFilterBody,
    c: Container = Depends(get_container),
    p: Principal = Depends(get_principal),
) -> Any:
    _need_accounts(c)
    _need_user(c, p)
    return c.collab.save_filter(p.user_id, p.org_id, body.name, body.scope, body.params)


@router.delete("/saved-filters/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved(
    filter_id: str, c: Container = Depends(get_container), p: Principal = Depends(get_principal)
) -> Response:
    _need_accounts(c)
    _need_user(c, p)
    c.collab.delete_filter(p.user_id, p.org_id, filter_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class WebhookCreate(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = Field(min_length=1, max_length=10)


class WebhookPatch(BaseModel):
    url: str | None = Field(default=None, max_length=500)
    events: list[str] | None = None
    active: bool | None = None


@router.get("/webhooks")
def list_webhooks(c: Container = Depends(get_container), p: Principal = Depends(admin)) -> Any:
    _need_accounts(c)
    return {"enabled": c.webhooks.enabled, "items": c.webhooks.list_all(p.org_id)}


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
def create_webhook(
    body: WebhookCreate, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    """The signing secret is in this response (and again on rotation), nowhere else."""
    _need_accounts(c)
    return c.webhooks.create(p.org_id, body.url, body.events, actor=p.user_id)


@router.patch("/webhooks/{webhook_id}")
def patch_webhook(
    webhook_id: str,
    body: WebhookPatch,
    c: Container = Depends(get_container),
    p: Principal = Depends(admin),
) -> Any:
    _need_accounts(c)
    return c.webhooks.update(
        webhook_id, p.org_id, actor=p.user_id, active=body.active, events=body.events, url=body.url
    )


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: str, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Response:
    _need_accounts(c)
    c.webhooks.delete(webhook_id, p.org_id, actor=p.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/webhooks/{webhook_id}/rotate")
def rotate_webhook(
    webhook_id: str, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    _need_accounts(c)
    return c.webhooks.rotate(webhook_id, p.org_id, actor=p.user_id)


@router.post("/webhooks/{webhook_id}/test", status_code=status.HTTP_202_ACCEPTED)
def test_webhook(
    webhook_id: str, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    _need_accounts(c)
    c.webhooks.ping(webhook_id, p.org_id)
    return {"queued": True}


@router.get("/webhooks/{webhook_id}/deliveries")
def webhook_deliveries(
    webhook_id: str, c: Container = Depends(get_container), p: Principal = Depends(admin)
) -> Any:
    _need_accounts(c)
    return c.webhooks.deliveries(webhook_id, p.org_id)


@router.post("/webhooks/{webhook_id}/deliveries/{delivery_id}/redeliver")
def redeliver(
    webhook_id: str,
    delivery_id: str,
    c: Container = Depends(get_container),
    p: Principal = Depends(admin),
) -> Any:
    _need_accounts(c)
    c.webhooks.redeliver(webhook_id, delivery_id, p.org_id)
    return {"queued": True}


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
