"""Accounts mode: personal tokens, roles, membership, the kill switch, and the audit trail."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from tests.screening.integration.api.accounts_world import (
    build_world,
    make_member,
)

from ipo_engine.screening.core.security import Role
from ipo_engine.screening.services.accounts import AccountError
from ipo_engine.screening.db.models import ApiTokenRow, AuditEventRow


def test_accounts_mode_has_no_anonymous_local_admin(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    assert w.client.get("/api/v1/cases").status_code == 401
    assert (
        w.client.get("/api/v1/cases", headers={"Authorization": "Bearer nope"}).status_code == 401
    )
    assert w.client.get("/api/v1/cases", headers=w.a.h).status_code == 200


def test_legacy_unversioned_routes_are_not_served_in_accounts_mode(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    assert w.client.post("/screen", json={}, headers=w.a.h).status_code == 404
    assert (
        w.client.get("/reports/00000000-0000-0000-0000-000000000000", headers=w.a.h).status_code
        == 404
    )


def test_me_shows_the_organisation_and_role(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    me = w.client.get("/api/v1/me", headers=w.a.h).json()
    assert me["user_id"] == w.a.user_id and me["role"] == "admin" and me["org_id"] == w.a.org_id
    assert w.client.get("/api/v1/org", headers=w.a.h).json()["name"] == "Alpha Capital"


def test_token_is_shown_once_and_stored_only_as_a_hash(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    made = w.client.post("/api/v1/tokens", json={"name": "ci"}, headers=w.a.h)
    assert made.status_code == 201
    secret = made.json()["token"]
    assert secret.startswith("ipo_") and len(secret) > 40
    listing = w.client.get("/api/v1/tokens", headers=w.a.h).json()
    assert all("token" not in row and "token_hash" not in row for row in listing)
    with w.client.app.state.container.db.session() as s:  # type: ignore[attr-defined]
        stored = s.execute(select(ApiTokenRow.token_hash, ApiTokenRow.prefix)).all()
    assert all(secret not in h and secret != p for h, p in stored)
    assert all(len(h) == 64 for h, _ in stored)
    assert (
        w.client.get("/api/v1/me", headers={"Authorization": f"Bearer {secret}"}).status_code == 200
    )


def test_revoked_expired_and_suspended_credentials_are_refused_alike(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    acc = w.accounts
    mem = make_member(w.client, w.a.org_id, "eve@alpha.example", Role.ANALYST)
    assert w.client.get("/api/v1/cases", headers=mem.h).status_code == 200

    # revoked
    tok = acc.create_token(org_id=w.a.org_id, user_id=mem.user_id, name="x")
    assert (
        w.client.get(
            "/api/v1/cases", headers={"Authorization": f"Bearer {tok['token']}"}
        ).status_code
        == 200
    )
    acc.revoke_token(tok["id"], user_id=mem.user_id, org_id=w.a.org_id, actor="t")
    r_revoked = w.client.get("/api/v1/cases", headers={"Authorization": f"Bearer {tok['token']}"})

    # expired
    old = acc.create_token(org_id=w.a.org_id, user_id=mem.user_id, name="old", days=1)
    with w.client.app.state.container.db.session() as s:  # type: ignore[attr-defined]
        row = s.get(ApiTokenRow, old["id"])
        row.expires_at = datetime.now(tz=UTC) - timedelta(minutes=1)
    r_expired = w.client.get("/api/v1/cases", headers={"Authorization": f"Bearer {old['token']}"})

    # suspended user
    acc.set_user_status(mem.user_id, "suspended", actor="t")
    r_suspended = w.client.get("/api/v1/cases", headers=mem.h)

    unknown = w.client.get("/api/v1/cases", headers={"Authorization": "Bearer ipo_unknown"})
    assert {r.status_code for r in (r_revoked, r_expired, r_suspended, unknown)} == {401}

    def shape(r: Any) -> Any:
        err = dict(r.json()["error"])
        err.pop("request_id", None)
        return err

    assert all(shape(r) == shape(unknown) for r in (r_revoked, r_expired, r_suspended)), (
        "the response must not reveal why a credential failed"
    )

    acc.set_user_status(mem.user_id, "active", actor="t")
    assert w.client.get("/api/v1/cases", headers=mem.h).status_code == 200  # reinstated


def test_removing_a_member_revokes_their_tokens_immediately(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    mem = make_member(w.client, w.a.org_id, "sam@alpha.example", Role.ANALYST)
    assert w.client.get("/api/v1/cases", headers=mem.h).status_code == 200
    assert w.client.delete(f"/api/v1/org/members/{mem.user_id}", headers=w.a.h).status_code == 204
    assert w.client.get("/api/v1/cases", headers=mem.h).status_code == 401


def test_a_token_never_outranks_its_owner_even_after_a_demotion(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    mem = make_member(w.client, w.a.org_id, "dan@alpha.example", Role.REVIEWER)
    assert w.client.get("/api/v1/org/members", headers=mem.h).status_code == 200  # reviewer
    w.client.patch(f"/api/v1/org/members/{mem.user_id}", json={"role": "viewer"}, headers=w.a.h)
    assert w.client.get("/api/v1/org/members", headers=mem.h).status_code == 403
    too_high = w.client.post("/api/v1/tokens", json={"name": "t", "role": "admin"}, headers=mem.h)
    assert too_high.status_code == 422  # cannot mint above one's own role


def test_roles_gate_the_account_routes(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    viewer = make_member(w.client, w.a.org_id, "vi@alpha.example", Role.VIEWER)
    assert w.client.patch("/api/v1/org", json={"name": "X"}, headers=viewer.h).status_code == 403
    assert (
        w.client.post(
            "/api/v1/org/members", json={"email": "n@a.example", "role": "viewer"}, headers=viewer.h
        ).status_code
        == 403
    )
    assert w.client.patch("/api/v1/org", json={"name": "Alpha 2"}, headers=w.a.h).status_code == 200


def test_an_organisation_keeps_at_least_one_admin(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    r = w.client.delete(f"/api/v1/org/members/{w.a.user_id}", headers=w.a.h)
    assert r.status_code == 422 and "at least one admin" in r.text
    r = w.client.patch(f"/api/v1/org/members/{w.a.user_id}", json={"role": "viewer"}, headers=w.a.h)
    assert r.status_code == 422


def test_members_of_other_organisations_are_invisible(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    emails = {m["email"] for m in w.client.get("/api/v1/org/members", headers=w.a.h).json()}
    assert emails == {"ann@alpha.example"}
    r = w.client.delete(f"/api/v1/org/members/{w.b.user_id}", headers=w.a.h)
    assert r.status_code == 404
    r = w.client.delete(
        f"/api/v1/tokens/{w.accounts.list_tokens(w.b.user_id)[0]['id']}", headers=w.a.h
    )
    assert r.status_code in (403, 404)
    assert w.client.get("/api/v1/me", headers=w.b.h).status_code == 200  # b untouched


def test_audit_records_the_real_user_and_organisation(app_factory: Any) -> None:
    w = build_world(app_factory)
    with w.client.app.state.container.db.session() as s:  # type: ignore[attr-defined]
        rows = (
            s.execute(select(AuditEventRow).where(AuditEventRow.case_id == w.case_a))
            .scalars()
            .all()
        )
        assert rows and all(r.org_id == w.a.org_id for r in rows)
        created = next(r for r in rows if r.action == "case.created")
        assert created.actor == w.a.user_id  # a user id, not "api-user"
        token_events = (
            s.execute(select(AuditEventRow).where(AuditEventRow.action == "token.created"))
            .scalars()
            .all()
        )
        assert token_events and all(e.org_id for e in token_events)
    activity = w.client.get("/api/v1/dashboard", headers=w.b.h).json()["recent_activity"]
    assert activity == [] or all(e["case_id"] != w.case_a for e in activity)


def test_the_sole_admin_cannot_leave_the_organisation_adminless_through_add_member(
    app_factory: Any,
) -> None:
    """POST /org/members with an existing member is a role change and obeys the same guards."""
    w = build_world(app_factory, seed_a=False)
    r = w.client.post(
        "/api/v1/org/members", json={"email": "ann@alpha.example", "role": "viewer"}, headers=w.a.h
    )
    assert r.status_code == 422, r.text
    assert w.accounts.role_of(w.a.org_id, w.a.user_id) == Role.ADMIN


def test_the_service_refuses_to_demote_the_last_admin(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    with pytest.raises(AccountError, match="at least one admin"):
        w.accounts.add_member(w.a.org_id, w.a.user_id, Role.VIEWER, actor="test")


def test_an_admin_who_is_not_the_owner_cannot_remove_or_demote_the_owner(
    app_factory: Any,
) -> None:
    w = build_world(app_factory, seed_a=False)
    user = w.accounts.get_or_create_user("second-admin@alpha.example")
    w.accounts.add_member(w.a.org_id, user["id"], Role.ADMIN, actor="test", owner=False)
    tok = w.accounts.create_token(org_id=w.a.org_id, user_id=user["id"], name="t")["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert w.accounts.is_owner(w.a.org_id, w.a.user_id)
    assert not w.accounts.is_owner(w.a.org_id, user["id"])
    assert w.client.delete(f"/api/v1/org/members/{w.a.user_id}", headers=h).status_code == 403
    r = w.client.patch(
        f"/api/v1/org/members/{w.a.user_id}", json={"role": "viewer"}, headers=h
    )
    assert r.status_code == 403
    assert w.client.get("/api/v1/me", headers=w.a.h).status_code == 200  # the owner still works
    # the owner may manage the second admin
    assert (
        w.client.delete(f"/api/v1/org/members/{user['id']}", headers=w.a.h).status_code == 204
    )


def test_a_token_always_expires_and_a_child_never_outlives_its_parent(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    r = w.client.post("/api/v1/tokens", json={"name": "forever", "days": None}, headers=w.a.h)
    assert r.status_code == 422  # no unlimited tokens through the API
    parent = w.client.post("/api/v1/tokens", json={"name": "p", "days": 2}, headers=w.a.h).json()
    ph = {"Authorization": f"Bearer {parent['token']}"}
    child = w.client.post("/api/v1/tokens", json={"name": "c", "days": 90}, headers=ph).json()
    assert child["expires_at"] <= parent["expires_at"]


def test_revoking_a_token_revokes_what_it_minted(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False)
    parent = w.client.post("/api/v1/tokens", json={"name": "p"}, headers=w.a.h).json()
    ph = {"Authorization": f"Bearer {parent['token']}"}
    child = w.client.post("/api/v1/tokens", json={"name": "c"}, headers=ph).json()
    grandchild = w.client.post(
        "/api/v1/tokens",
        json={"name": "g"},
        headers={"Authorization": f"Bearer {child['token']}"},
    ).json()
    for t in (child, grandchild):
        assert w.client.get("/api/v1/me", headers={"Authorization": f"Bearer {t['token']}"}).status_code == 200
    assert w.client.delete(f"/api/v1/tokens/{parent['id']}", headers=w.a.h).status_code == 204
    for t in (parent, child, grandchild):
        r = w.client.get("/api/v1/me", headers={"Authorization": f"Bearer {t['token']}"})
        assert r.status_code == 401
    assert w.client.get("/api/v1/me", headers=w.a.h).status_code == 200  # the admin's own token
