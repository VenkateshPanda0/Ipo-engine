"""Shared set-up for the accounts tests: two organisations, each with an admin and a token."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from fastapi.testclient import TestClient
from tests.screening.fixtures.pdf_factory import standard_drhp

from ipo_engine.screening.core.security import Role


@dataclass
class Member:
    user_id: str
    org_id: str
    token: str

    @property
    def h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class World:
    client: TestClient
    a: Member  # admin of org A
    b: Member  # admin of org B
    case_a: str = ""
    document_a: str = ""
    report_a: str = ""
    item_a: str = ""
    comment_a: str = ""

    @property
    def accounts(self) -> Any:
        return self.client.app.state.container.accounts  # type: ignore[attr-defined]


def make_member(client: TestClient, org_id: str, email: str, role: Role = Role.ADMIN) -> Member:
    acc = client.app.state.container.accounts  # type: ignore[attr-defined]
    user = acc.get_or_create_user(email)
    acc.add_member(org_id, user["id"], role, actor="test", owner=role == Role.ADMIN)
    tok = acc.create_token(org_id=org_id, user_id=user["id"], name="test")
    return Member(user["id"], org_id, tok["token"])


def build_world(app_factory: Any, *, seed_a: bool = True, **settings: Any) -> World:
    client = cast(TestClient, app_factory(ACCOUNTS_ENABLED="true", **settings))
    acc = client.app.state.container.accounts  # type: ignore[attr-defined]
    org_a = acc.create_org("Alpha Capital")["id"]
    org_b = acc.create_org("Beta Advisors")["id"]
    world = World(
        client=client,
        a=make_member(client, org_a, "ann@alpha.example"),
        b=make_member(client, org_b, "bob@beta.example"),
    )
    if seed_a:
        seed_org_a(world)
    return world


def seed_org_a(w: World) -> None:
    """One case with a document, extraction review items and a screening report, all in org A."""
    c = w.client
    case = c.post("/api/v1/cases", json={"company_name": "Alpha Target Ltd"}, headers=w.a.h).json()
    w.case_a = case["id"]
    doc = c.post(
        f"/api/v1/cases/{w.case_a}/documents",
        files={"file": ("drhp.pdf", standard_drhp(), "application/pdf")},
        headers=w.a.h,
    ).json()
    w.document_a = doc["id"]
    w.report_a = c.post(f"/api/v1/cases/{w.case_a}/screenings", headers=w.a.h).json()["report_id"]
    items = c.get("/api/v1/review-items", headers=w.a.h).json()
    assert items, "the synthetic filing must raise review items"
    w.item_a = items[0]["id"]
    comment = c.post(
        f"/api/v1/cases/{w.case_a}/comments", json={"body": "First note"}, headers=w.a.h
    )
    assert comment.status_code == 201, comment.text
    w.comment_a = comment.json()["id"]
