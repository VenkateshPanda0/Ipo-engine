"""
Tenant isolation, checked mechanically.

Every route in the table that takes an id is called with another organisation's id and must answer
404, the same as for an id that does not exist. The test builds its list of routes from the running
application, so a route added later is covered without anyone remembering to add it here; a route
with an id this suite cannot place fails the test instead of being skipped. A second test breaks the
check on purpose and requires the walker to notice, so a passing result means something.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from tests.screening.integration.api.accounts_world import World, build_world

from ipo_engine.screening.services import tenancy

_PARAM = re.compile(r"\{([a-z_]+)\}")
_UNSCOPED = set(tenancy.UNSCOPED_PARAMS)


def _routes(world: World) -> list[tuple[str, str]]:
    """Every (method, path) the application serves under /api/v1, read from its OpenAPI schema."""
    paths = world.client.get("/openapi.json").json()["paths"]
    return [
        (method.upper(), path)
        for path, ops in sorted(paths.items())
        if path.startswith("/api/v1")
        for method in sorted(ops)
        if method in {"get", "post", "put", "patch", "delete"}
    ]


def _ids(world: World) -> dict[str, str]:
    return {
        "case_id": world.case_a,
        "document_id": world.document_a,
        "report_id": world.report_a,
        "item_id": world.item_a,
        "page": "1",
        "rule_id": "REG-1",
        "review_id": "00000000-0000-0000-0000-000000000000",
    }


def _fill(path: str, ids: dict[str, str]) -> str:
    return _PARAM.sub(lambda m: ids[m.group(1)], path)


def _account_route(path: str) -> bool:
    return path.split("/api/v1", 1)[1].startswith(("/org", "/tokens", "/me", "/auth"))


def foreign_hits(world: World) -> list[tuple[str, str, int]]:
    """Calls org B makes with org A's ids. Anything that is not 404 is a leak."""
    ids = _ids(world)
    leaks: list[tuple[str, str, int]] = []
    for method, path in _routes(world):
        params = set(_PARAM.findall(path))
        if not (params - _UNSCOPED) or _account_route(path):
            continue
        url = _fill(path, ids)
        r = world.client.request(method, url, headers=world.b.h, json={})
        if r.status_code != 404:
            leaks.append((method, url, r.status_code))
    return leaks


@pytest.fixture
def world(app_factory: Any) -> World:
    return build_world(app_factory)


def test_every_route_with_an_id_is_known_to_the_scope_rules(world: World) -> None:
    unknown = {
        (m, p, name)
        for m, p in _routes(world)
        for name in _PARAM.findall(p)
        if name not in tenancy.SCOPED_PARAMS and name not in _UNSCOPED and not _account_route(p)
    }
    assert not unknown, f"routes with ids no scope rule covers: {sorted(unknown)}"


def test_another_organisation_gets_404_on_every_route_taking_an_id(world: World) -> None:
    scoped = [
        (m, p)
        for m, p in _routes(world)
        if set(_PARAM.findall(p)) - _UNSCOPED and not _account_route(p)
    ]
    assert len(scoped) >= 20, "the walker must actually find the id routes"
    assert foreign_hits(world) == []


def test_the_owner_still_reaches_what_the_other_organisation_cannot(world: World) -> None:
    h = world.a.h
    assert world.client.get(f"/api/v1/cases/{world.case_a}", headers=h).status_code == 200
    assert world.client.get(f"/api/v1/documents/{world.document_a}", headers=h).status_code == 200
    assert world.client.get(f"/api/v1/reports/{world.report_a}", headers=h).status_code == 200


def test_lists_and_dashboard_show_only_the_callers_organisation(world: World) -> None:
    for org, expect_cases in ((world.a, 1), (world.b, 0)):
        c = world.client
        cases = c.get("/api/v1/cases", headers=org.h).json()
        assert cases["total"] == expect_cases and len(cases["items"]) == expect_cases
        assert len(c.get("/api/v1/documents", headers=org.h).json()) == expect_cases
        assert (len(c.get("/api/v1/reports", headers=org.h).json()) > 0) == bool(expect_cases)
        assert (len(c.get("/api/v1/review-items", headers=org.h).json()) > 0) == bool(expect_cases)
        dash = c.get("/api/v1/dashboard", headers=org.h).json()
        assert dash["cases_total"] == expect_cases
        assert (dash["reports_total"] > 0) == bool(expect_cases)
        assert (dash["open_review_items"] > 0) == bool(expect_cases)
        activity_cases = {e["case_id"] for e in dash["recent_activity"]}
        assert (world.case_a in activity_cases) == bool(expect_cases)


def test_a_case_filter_for_another_organisations_case_is_a_404(world: World) -> None:
    r = world.client.get(
        "/api/v1/review-items", params={"case_id": world.case_a}, headers=world.b.h
    )
    assert r.status_code == 404


def test_creating_a_case_puts_it_in_the_callers_organisation_only(world: World) -> None:
    made = world.client.post(
        "/api/v1/cases", json={"company_name": "Beta Target Ltd"}, headers=world.b.h
    ).json()
    assert world.client.get(f"/api/v1/cases/{made['id']}", headers=world.b.h).status_code == 200
    assert world.client.get(f"/api/v1/cases/{made['id']}", headers=world.a.h).status_code == 404
    names = {
        x["company_name"]
        for x in world.client.get("/api/v1/cases", headers=world.a.h).json()["items"]
    }
    assert names == {"Alpha Target Ltd"}


def test_the_walker_has_teeth(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """With the ownership check broken, the same walk must report leaks."""
    monkeypatch.setattr(
        "ipo_engine.screening.api.scope.owner_org", lambda db, name, value: world.b.org_id
    )
    leaks = foreign_hits(world)
    assert len(leaks) >= 10, leaks
