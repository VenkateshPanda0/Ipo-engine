"""Assignments, comments, notifications, saved searches, settings, four-eyes, onboarding, usage."""

from __future__ import annotations

from typing import Any

import pytest
from tests.screening.integration.api.accounts_world import World, build_world, make_member

from ipo_engine.screening.core.security import Role


@pytest.fixture
def world(app_factory: Any) -> World:
    return build_world(app_factory)


def _team(w: World) -> tuple[Any, Any]:
    analyst = make_member(w.client, w.a.org_id, "ana@alpha.example", Role.ANALYST)
    viewer = make_member(w.client, w.a.org_id, "vic@alpha.example", Role.VIEWER)
    return analyst, viewer


# ------------------------------------------------------------------ assignment
def test_assigning_a_case_shows_in_lists_filters_and_notifies_the_assignee(world: World) -> None:
    ana, _ = _team(world)
    r = world.client.put(
        f"/api/v1/cases/{world.case_a}/assignee",
        json={"assignee_id": ana.user_id},
        headers=world.a.h,
    )
    assert r.status_code == 200
    case = world.client.get(f"/api/v1/cases/{world.case_a}", headers=world.a.h).json()
    assert case["assignee_id"] == ana.user_id
    mine = world.client.get("/api/v1/cases", params={"assignee": "me"}, headers=ana.h).json()
    assert [c["id"] for c in mine["items"]] == [world.case_a]
    assert (
        world.client.get("/api/v1/cases", params={"assignee": "me"}, headers=world.a.h).json()[
            "total"
        ]
        == 0
    )
    note = world.client.get("/api/v1/notifications", headers=ana.h).json()
    assert note["unread"] == 1 and "Alpha Target" in note["items"][0]["title"]
    assert world.client.get("/api/v1/dashboard", headers=ana.h).json()["assigned_to_me"] == 1


def test_a_case_can_only_go_to_a_member_and_can_be_unassigned(world: World) -> None:
    stranger = world.b.user_id
    url = f"/api/v1/cases/{world.case_a}/assignee"
    assert (
        world.client.put(url, json={"assignee_id": stranger}, headers=world.a.h).status_code == 422
    )
    assert (
        world.client.put(url, json={"assignee_id": world.a.user_id}, headers=world.a.h).status_code
        == 200
    )
    assert world.client.put(url, json={"assignee_id": None}, headers=world.a.h).status_code == 200
    assert (
        world.client.get(f"/api/v1/cases/{world.case_a}", headers=world.a.h).json()["assignee_id"]
        is None
    )


def test_a_viewer_cannot_assign_or_comment(world: World) -> None:
    _, viewer = _team(world)
    assert (
        world.client.put(
            f"/api/v1/cases/{world.case_a}/assignee", json={"assignee_id": None}, headers=viewer.h
        ).status_code
        == 403
    )
    assert (
        world.client.post(
            f"/api/v1/cases/{world.case_a}/comments", json={"body": "hi"}, headers=viewer.h
        ).status_code
        == 403
    )
    assert (
        world.client.get(f"/api/v1/cases/{world.case_a}/comments", headers=viewer.h).status_code
        == 200
    )


# -------------------------------------------------------------------- comments
def test_comments_are_listed_in_order_with_their_author(world: World) -> None:
    ana, _ = _team(world)
    world.client.post(
        f"/api/v1/cases/{world.case_a}/comments", json={"body": "Second"}, headers=ana.h
    )
    items = world.client.get(f"/api/v1/cases/{world.case_a}/comments", headers=world.a.h).json()
    assert [i["body"] for i in items] == ["First note", "Second"]
    assert items[1]["author_id"] == ana.user_id and items[1]["author"] == "ana@alpha.example"


def test_a_comment_notifies_the_case_owner_and_assignee_but_not_its_author(world: World) -> None:
    ana, _ = _team(world)
    world.client.put(
        f"/api/v1/cases/{world.case_a}/assignee",
        json={"assignee_id": ana.user_id},
        headers=world.a.h,
    )
    world.client.post(
        f"/api/v1/cases/{world.case_a}/comments", json={"body": "Looks odd"}, headers=ana.h
    )
    admin_notes = world.client.get("/api/v1/notifications", headers=world.a.h).json()
    assert any(n["kind"] == "comment" for n in admin_notes["items"])  # the case's creator
    ana_notes = world.client.get("/api/v1/notifications", headers=ana.h).json()
    assert [n["kind"] for n in ana_notes["items"]] == ["assigned"]  # not told of her own comment


def test_comments_are_validated_and_removable_by_author_or_admin_only(world: World) -> None:
    ana, _ = _team(world)
    url = f"/api/v1/cases/{world.case_a}/comments"
    assert world.client.post(url, json={"body": "   "}, headers=ana.h).status_code == 422
    assert world.client.post(url, json={"body": "x" * 5001}, headers=ana.h).status_code == 422
    mine = world.client.post(url, json={"body": "mine"}, headers=ana.h).json()["id"]
    other = make_member(world.client, world.a.org_id, "bo@alpha.example", Role.ANALYST)
    assert (
        world.client.delete(f"{url}/{mine}", headers=other.h).status_code == 422
    )  # neither author nor admin
    assert world.client.delete(f"{url}/{mine}", headers=ana.h).status_code == 204
    assert (
        world.client.delete(f"{url}/{world.comment_a}", headers=world.a.h).status_code == 204
    )  # admin
    assert world.client.get(url, headers=world.a.h).json() == []


def test_comments_stay_inside_their_organisation(world: World) -> None:
    assert (
        world.client.get(f"/api/v1/cases/{world.case_a}/comments", headers=world.b.h).status_code
        == 404
    )
    assert (
        world.client.post(
            f"/api/v1/cases/{world.case_a}/comments", json={"body": "intruder"}, headers=world.b.h
        ).status_code
        == 404
    )


# --------------------------------------------------------------- notifications
def test_notifications_can_be_read_one_by_one_or_all_and_are_private(world: World) -> None:
    ana, _ = _team(world)
    for n in range(3):
        world.client.put(
            f"/api/v1/cases/{world.case_a}/assignee",
            json={"assignee_id": ana.user_id if n % 2 == 0 else world.a.user_id},
            headers=world.a.h,
        )
    notes = world.client.get("/api/v1/notifications", headers=ana.h).json()
    assert notes["unread"] == 2
    first = notes["items"][0]["id"]
    assert (
        world.client.post(f"/api/v1/notifications/{first}/read", headers=world.a.h).status_code
        == 404
    )
    assert world.client.post(f"/api/v1/notifications/{first}/read", headers=ana.h).json() == {
        "marked": 1
    }
    assert (
        world.client.get("/api/v1/notifications", params={"unread": "true"}, headers=ana.h).json()[
            "unread"
        ]
        == 1
    )
    assert world.client.post("/api/v1/notifications/read", headers=ana.h).json() == {"marked": 1}


# -------------------------------------------------------------- saved searches
def test_saved_searches_belong_to_one_person_in_one_organisation(world: World) -> None:
    ana, _ = _team(world)
    body = {"name": "My drafts", "scope": "cases", "params": {"status": "draft", "mine": True}}
    made = world.client.post("/api/v1/saved-filters", json=body, headers=ana.h)
    assert made.status_code == 201
    again = world.client.post(
        "/api/v1/saved-filters", json={**body, "params": {"q": "acme"}}, headers=ana.h
    )
    assert again.json()["id"] == made.json()["id"] and again.json()["params"] == {
        "q": "acme"
    }  # same name: updated
    assert len(world.client.get("/api/v1/saved-filters", headers=ana.h).json()) == 1
    assert world.client.get("/api/v1/saved-filters", headers=world.a.h).json() == []
    fid = made.json()["id"]
    assert world.client.delete(f"/api/v1/saved-filters/{fid}", headers=world.a.h).status_code == 404
    assert world.client.delete(f"/api/v1/saved-filters/{fid}", headers=ana.h).status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "scope": "cases", "params": {}},
        {"name": "x", "scope": "everything", "params": {}},
        {"name": "x", "scope": "cases", "params": {"sql": "drop table"}},
        {"name": "x", "scope": "cases", "params": {"q": {"nested": 1}}},
    ],
)
def test_bad_saved_searches_are_refused(world: World, body: dict[str, Any]) -> None:
    assert (
        world.client.post("/api/v1/saved-filters", json=body, headers=world.a.h).status_code == 422
    )


# ---------------------------------------------------- settings and four-eyes
def test_settings_default_validate_and_need_an_admin(world: World) -> None:
    ana, _ = _team(world)
    assert world.client.get("/api/v1/org/settings", headers=ana.h).json() == {
        "four_eyes": False,
        "webhooks_enabled": True,
    }
    assert (
        world.client.patch(
            "/api/v1/org/settings", json={"four_eyes": True}, headers=ana.h
        ).status_code
        == 403
    )
    assert (
        world.client.patch(
            "/api/v1/org/settings", json={"four_eyes": "yes please"}, headers=world.a.h
        ).status_code
        == 422
    )
    ok = world.client.patch("/api/v1/org/settings", json={"four_eyes": True}, headers=world.a.h)
    assert ok.json()["four_eyes"] is True
    assert world.client.get("/api/v1/org/settings", headers=world.b.h).json()["four_eyes"] is False


def test_with_four_eyes_the_person_who_ran_the_screening_cannot_sign_it_off(world: World) -> None:
    rev = make_member(world.client, world.a.org_id, "rev@alpha.example", Role.REVIEWER)
    body = {
        "reviewer_name": "R",
        "final_decision": "proceed",
        "rationale": "Checked.",
        "conditions": [],
    }
    url = f"/api/v1/reports/{world.report_a}/sign-off"
    world.client.patch("/api/v1/org/settings", json={"four_eyes": True}, headers=world.a.h)
    refused = world.client.post(url, json=body, headers=world.a.h)  # ann ran the screening
    assert refused.status_code == 409 and "second person" in refused.text
    assert world.client.post(url, json=body, headers=rev.h).status_code == 200
    world.client.patch("/api/v1/org/settings", json={"four_eyes": False}, headers=world.a.h)


# ------------------------------------------------- onboarding, usage, isolation
def test_onboarding_ticks_off_what_has_been_done(world: World) -> None:
    steps = {
        s["id"]: s["done"]
        for s in world.client.get("/api/v1/onboarding", headers=world.a.h).json()["steps"]
    }
    assert steps == {
        "create_case": True,
        "upload_document": True,
        "run_screening": True,
        "invite_teammate": False,
        "create_token": True,
    }
    empty = world.client.get("/api/v1/onboarding", headers=world.b.h).json()
    assert (
        not any(s["done"] for s in empty["steps"] if s["id"] != "create_token")
        and not empty["complete"]
    )
    world.client.post(
        "/api/v1/org/invitations",
        json={"email": "n@x.example", "role": "viewer"},
        headers=world.a.h,
    )
    done = world.client.get("/api/v1/onboarding", headers=world.a.h).json()
    assert done["complete"] is True


def test_usage_counts_only_this_organisation(world: World) -> None:
    a = world.client.get("/api/v1/org/usage", headers=world.a.h).json()
    b = world.client.get("/api/v1/org/usage", headers=world.b.h).json()
    assert a["cases_total"] == 1 and a["documents_uploaded"] == 1 and a["screenings_run"] == 1
    assert a["pages_processed"] >= 1 and a["members"] == 1 and a["audit_events"] > 0
    assert b["cases_total"] == 0 and b["documents_uploaded"] == 0 and b["pages_processed"] == 0
    ana, _ = _team(world)
    assert world.client.get("/api/v1/org/usage", headers=ana.h).status_code == 403
