"""Spreadsheet exports (CSV, XLSX) and share links."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree import ElementTree

import pytest
from tests.screening.integration.api.accounts_world import World, build_world, make_member

from ipo_engine.screening.core.security import Role
from ipo_engine.screening.db.models import ShareLinkRow
from ipo_engine.screening.services.documents import RateLimiter
from ipo_engine.screening.services.tabular import cell_text, to_csv, to_xlsx


@pytest.fixture
def world(app_factory: Any) -> World:
    return build_world(app_factory)


# ------------------------------------------------------------------ the writers
@pytest.mark.parametrize("text", ["=1+1", "+cmd", "-2", "@SUM(A1)", "\tx", "\rx"])
def test_anything_a_spreadsheet_could_run_is_turned_into_text(text: str) -> None:
    assert cell_text(text) == "'" + text
    assert cell_text("Acme Ltd") == "Acme Ltd" and cell_text(None) == "" and cell_text(5) == "5"


def test_csv_round_trips_awkward_text_and_has_a_bom_for_excel() -> None:
    rows = [['Acme, "Quoted" Ltd', "line\nbreak", "₹ 5 crore"]]
    raw = to_csv(["a", "b", "c"], rows)
    assert raw.startswith(b"\xef\xbb\xbf")
    back = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert back == [["a", "b", "c"], rows[0]]


def test_xlsx_is_a_valid_workbook_that_keeps_text_and_neutralises_formulas() -> None:
    raw = to_xlsx("Cases", ["Name", "N"], [['=HYPERLINK("x")', "a & <b>"], ["plain", "\x00bad"]])
    z = zipfile.ZipFile(io.BytesIO(raw))
    assert z.testzip() is None
    for name in z.namelist():
        ElementTree.fromstring(z.read(name))  # every part is well-formed XML
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert "'=HYPERLINK" in sheet and "a &amp; &lt;b&gt;" in sheet and "\x00" not in sheet
    assert 'name="Cases"' in z.read("xl/workbook.xml").decode()


# ------------------------------------------------------------------- the routes
def test_the_case_list_exports_as_csv_and_xlsx_for_the_callers_organisation_only(
    world: World,
) -> None:
    world.client.post("/api/v1/cases", json={"company_name": "=EVIL()"}, headers=world.a.h)
    world.client.post("/api/v1/cases", json={"company_name": "Beta Only Ltd"}, headers=world.b.h)
    r = world.client.get("/api/v1/exports/cases", headers=world.a.h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="cases.csv"' in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    names = {row[0] for row in rows[1:]}
    assert names == {"Alpha Target Ltd", "'=EVIL()"}  # org B's case is absent; the formula is text
    x = world.client.get("/api/v1/exports/cases", params={"format": "xlsx"}, headers=world.a.h)
    assert x.content[:2] == b"PK" and zipfile.ZipFile(io.BytesIO(x.content)).testzip() is None


def test_exports_honour_the_same_filters_as_the_list(world: World) -> None:
    world.client.post("/api/v1/cases", json={"company_name": "Zeta Ltd"}, headers=world.a.h)
    r = world.client.get("/api/v1/exports/cases", params={"q": "zeta"}, headers=world.a.h)
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert [row[0] for row in rows[1:]] == ["Zeta Ltd"]


def test_the_report_list_exports_and_an_unknown_export_is_404(world: World) -> None:
    r = world.client.get("/api/v1/exports/reports", headers=world.a.h)
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Company" and len(rows) == 2 and rows[1][6] == world.report_a
    assert (
        len(
            list(
                csv.reader(
                    io.StringIO(
                        world.client.get(
                            "/api/v1/exports/reports", headers=world.b.h
                        ).content.decode("utf-8-sig")
                    )
                )
            )
        )
        == 1
    )  # header only
    assert world.client.get("/api/v1/exports/users", headers=world.a.h).status_code == 404
    assert (
        world.client.get(
            "/api/v1/exports/cases", params={"format": "pdf"}, headers=world.a.h
        ).status_code
        == 422
    )


def test_exports_need_a_credential(world: World) -> None:
    assert world.client.get("/api/v1/exports/cases").status_code == 401


# ---------------------------------------------------------------- share links
def _open(w: World, token: str) -> Any:
    return w.client.get(f"/api/v1/shared/{token}")  # no credentials at all


def test_a_share_link_shows_one_report_to_someone_without_an_account(world: World) -> None:
    r = _open(world, world.share_token_a)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Alpha Target" in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
    shares = world.client.get(f"/api/v1/reports/{world.report_a}/shares", headers=world.a.h).json()
    assert shares[0]["views"] == 1 and shares[0]["state"] == "live"
    assert "token" not in shares[0]  # the secret is never listed


def test_only_a_hash_of_the_link_is_stored(world: World) -> None:
    with world.client.app.state.container.db.session() as s:  # type: ignore[attr-defined]
        row = s.get(ShareLinkRow, world.share_a)
        assert row is not None and world.share_token_a not in (row.token_hash, row.id)
        assert len(row.token_hash) == 64


def test_revoked_expired_and_made_up_links_all_look_the_same(world: World) -> None:
    made = world.client.post(
        f"/api/v1/reports/{world.report_a}/shares", json={"days": 1}, headers=world.a.h
    ).json()
    with world.client.app.state.container.db.session() as s:  # type: ignore[attr-defined]
        row = s.get(ShareLinkRow, made["id"])
        assert row is not None
        row.expires_at = datetime.now(tz=UTC) - timedelta(minutes=1)
    revoked = world.client.post(
        f"/api/v1/reports/{world.report_a}/shares", json={"days": 2}, headers=world.a.h
    ).json()
    world.client.delete(
        f"/api/v1/reports/{world.report_a}/shares/{revoked['id']}", headers=world.a.h
    )
    answers = [
        _open(world, made["token"]),
        _open(world, revoked["token"]),
        _open(world, "x" * 43),
        _open(world, "short"),
    ]
    assert {r.status_code for r in answers} == {404}
    shapes = {(r.json()["error"]["code"], r.json()["error"]["message"]) for r in answers}
    assert len(shapes) == 1  # nothing tells the cases apart


def test_share_links_are_limited_in_lifetime_and_number(world: World) -> None:
    url = f"/api/v1/reports/{world.report_a}/shares"
    assert world.client.post(url, json={"days": 0}, headers=world.a.h).status_code == 422
    assert world.client.post(url, json={"days": 91}, headers=world.a.h).status_code == 422
    for _ in range(19):  # one already exists
        assert world.client.post(url, json={"days": 1}, headers=world.a.h).status_code == 201
    assert world.client.post(url, json={"days": 1}, headers=world.a.h).status_code == 422


def test_only_reviewers_make_links_and_other_organisations_cannot_touch_them(world: World) -> None:
    ana = make_member(world.client, world.a.org_id, "ana@alpha.example", Role.ANALYST)
    url = f"/api/v1/reports/{world.report_a}/shares"
    assert world.client.post(url, json={"days": 1}, headers=ana.h).status_code == 403
    assert world.client.post(url, json={"days": 1}, headers=world.b.h).status_code == 404
    assert world.client.get(url, headers=world.b.h).status_code == 404
    assert world.client.delete(f"{url}/{world.share_a}", headers=world.b.h).status_code == 404
    assert _open(world, world.share_token_a).status_code == 200  # still works


def test_the_public_route_is_rate_limited(world: World) -> None:
    world.client.app.state.container.public_limiter = RateLimiter(3)  # type: ignore[attr-defined]
    codes = [_open(world, "x" * 43).status_code for _ in range(5)]
    assert codes == [404, 404, 404, 429, 429]


def test_erasing_the_case_removes_its_links(world: World) -> None:
    world.client.delete(
        f"/api/v1/cases/{world.case_a}", params={"confirm": "Alpha Target Ltd"}, headers=world.a.h
    )
    assert _open(world, world.share_token_a).status_code == 404
