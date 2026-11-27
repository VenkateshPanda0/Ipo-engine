"""Export and erasure: what leaves, what is removed, what is kept, and who may ask."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from tests.screening.integration.api.accounts_world import World, build_world, make_member

from ipo_engine.screening.core.security import Role
from ipo_engine.screening.db.models import (
    ApiTokenRow,
    AuditEventRow,
    CaseDataVersionRow,
    CaseRow,
    DocumentRow,
    OrganisationRow,
    ReportRow,
    ReviewItemRow,
)


@pytest.fixture
def world(app_factory: Any) -> World:
    return build_world(app_factory)


def _count(w: World, model: Any, *where: Any) -> int:
    with w.client.app.state.container.db.session() as s:  # type: ignore[attr-defined]
        return int(s.execute(select(func.count()).select_from(model).where(*where)).scalar_one())


def _upload_same_pdf_to_org_b(w: World) -> str:
    """Org B uploads byte-for-byte the file org A holds (the generator is not deterministic)."""
    pdf = w.client.get(f"/api/v1/documents/{w.document_a}/content", headers=w.a.h).content
    assert pdf.startswith(b"%PDF")
    case = w.client.post("/api/v1/cases", json={"company_name": "Beta Target Ltd"}, headers=w.b.h)
    cid = case.json()["id"]
    r = w.client.post(
        f"/api/v1/cases/{cid}/documents",
        files={"file": ("drhp.pdf", pdf, "application/pdf")},
        headers=w.b.h,
    )
    assert r.status_code == 202
    return str(cid)


# ------------------------------------------------------------------------- export
def test_the_export_holds_the_organisations_data_and_nobody_elses(world: World) -> None:
    other = _upload_same_pdf_to_org_b(world)
    r = world.client.get("/api/v1/org/export", params={"include_files": "true"}, headers=world.a.h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {
        "manifest.json",
        "cases.json",
        "documents.json",
        "reports.json",
        "members.json",
    } <= names
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["counts"]["cases"] == 1 and manifest["counts"]["documents"] == 1
    assert manifest["counts"]["files"] == 1 and any(n.startswith("files/") for n in names)
    cases = json.loads(z.read("cases.json"))
    assert [c["company_name"] for c in cases] == ["Alpha Target Ltd"]
    blob = b"".join(z.read(n) for n in names if n.endswith(".json"))
    assert b"Beta Target" not in blob and other.encode() not in blob
    assert b"bob@beta.example" not in blob
    assert json.loads(z.read("members.json"))[0]["email"] == "ann@alpha.example"


def test_the_export_leaves_out_files_unless_asked_and_is_audited(world: World) -> None:
    r = world.client.get("/api/v1/org/export", headers=world.a.h)
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert not any(n.startswith("files/") for n in names)
    assert _count(world, AuditEventRow, AuditEventRow.action == "org.exported") == 1


def test_only_an_admin_may_export(world: World) -> None:
    rev = make_member(world.client, world.a.org_id, "rev@alpha.example", Role.REVIEWER)
    assert world.client.get("/api/v1/org/export", headers=rev.h).status_code == 403


def test_a_person_can_export_what_is_held_about_them_without_secrets(world: World) -> None:
    body = world.client.get("/api/v1/me/export", headers=world.a.h).json()
    assert body["user"]["email"] == "ann@alpha.example"
    assert body["organisations"][0]["name"] == "Alpha Capital"
    text_ = json.dumps(body)
    assert "token_hash" not in text_ and world.a.token not in text_ and "csrf" not in text_
    assert body["activity"], "their own actions are listed"


# ------------------------------------------------------------------------ erasure
def test_erasing_a_case_needs_its_exact_name(world: World) -> None:
    r = world.client.delete(
        f"/api/v1/cases/{world.case_a}", params={"confirm": "wrong"}, headers=world.a.h
    )
    assert r.status_code == 422 and "exact company name" in r.text
    assert _count(world, CaseRow) == 1


def test_erasing_removes_everything_under_the_case_and_keeps_the_record_of_it(
    world: World,
) -> None:
    sha = world.client.get(f"/api/v1/documents/{world.document_a}", headers=world.a.h).json()[
        "sha256"
    ]
    store = world.client.app.state.container.files  # type: ignore[attr-defined]
    assert store.exists(sha)
    r = world.client.delete(
        f"/api/v1/cases/{world.case_a}", params={"confirm": "Alpha Target Ltd"}, headers=world.a.h
    )
    assert r.status_code == 200, r.text
    erased = r.json()["erased"]
    assert erased["cases"] == 1 and erased["documents"] == 1 and erased["case_data_versions"] >= 1
    for model in (CaseRow, DocumentRow, ReportRow, ReviewItemRow, CaseDataVersionRow):
        assert _count(world, model) == 0, model
    assert not store.exists(sha), "the stored PDF is gone"
    assert world.client.get(f"/api/v1/cases/{world.case_a}", headers=world.a.h).status_code == 404
    with world.client.app.state.container.db.session() as s:  # type: ignore[attr-defined]
        event = s.execute(
            select(AuditEventRow).where(AuditEventRow.action == "case.erased")
        ).scalar_one()
    assert event.org_id == world.a.org_id and event.actor == world.a.user_id
    assert "removed" in event.details and "Alpha Target" not in json.dumps(event.details)


def test_a_file_another_organisation_also_holds_is_not_deleted(world: World) -> None:
    other_case = _upload_same_pdf_to_org_b(world)
    sha = world.client.get(f"/api/v1/documents/{world.document_a}", headers=world.a.h).json()[
        "sha256"
    ]
    world.client.delete(
        f"/api/v1/cases/{world.case_a}", params={"confirm": "Alpha Target Ltd"}, headers=world.a.h
    )
    assert world.client.app.state.container.files.exists(sha)  # type: ignore[attr-defined]
    assert world.client.get(f"/api/v1/cases/{other_case}", headers=world.b.h).status_code == 200
    docs = world.client.get(f"/api/v1/cases/{other_case}/documents", headers=world.b.h).json()
    assert docs and world.client.get(
        f"/api/v1/documents/{docs[0]['id']}/content", headers=world.b.h
    ).status_code in (200, 409)


def test_append_only_protection_is_back_after_an_erasure(world: World) -> None:
    keep = world.client.post("/api/v1/cases", json={"company_name": "Keep Ltd"}, headers=world.a.h)
    assert keep.status_code == 201
    world.client.delete(
        f"/api/v1/cases/{world.case_a}", params={"confirm": "Alpha Target Ltd"}, headers=world.a.h
    )
    db = world.client.app.state.container.db  # type: ignore[attr-defined]
    for sql in (
        "DELETE FROM case_data_versions",
        "UPDATE case_data_versions SET version = version + 1",
        "DELETE FROM audit_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"), db.engine.begin() as conn:
            conn.execute(text(sql))


def test_a_failed_erasure_changes_nothing_and_the_protection_stays(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    life = world.client.app.state.container.lifecycle  # type: ignore[attr-defined]

    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(life._files, "delete", boom)  # the file removal comes after the commit
    with pytest.raises(RuntimeError):
        life.erase_case(world.case_a, world.a.org_id, actor="t", confirm="Alpha Target Ltd")
    # rows are gone (committed), and the triggers are intact
    db = world.client.app.state.container.db  # type: ignore[attr-defined]
    with pytest.raises(DBAPIError, match="append-only"), db.engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_events"))


def test_only_an_admin_of_the_same_organisation_may_erase(world: World) -> None:
    rev = make_member(world.client, world.a.org_id, "rev@alpha.example", Role.REVIEWER)
    url = f"/api/v1/cases/{world.case_a}"
    assert (
        world.client.delete(url, params={"confirm": "Alpha Target Ltd"}, headers=rev.h).status_code
        == 403
    )
    assert (
        world.client.delete(
            url, params={"confirm": "Alpha Target Ltd"}, headers=world.b.h
        ).status_code
        == 404
    )
    assert _count(world, CaseRow) == 1


# ------------------------------------------------------------------- organisations
def test_deleting_an_organisation_switches_it_off_and_purging_erases_it(world: World) -> None:
    c = world.client
    assert c.delete("/api/v1/org", params={"confirm": "nope"}, headers=world.a.h).status_code == 422
    acc = c.app.state.container.accounts  # type: ignore[attr-defined]
    user = acc.get_or_create_user("adm2@alpha.example")
    acc.add_member(world.a.org_id, user["id"], Role.ADMIN, actor="t", owner=False)
    helper = acc.create_token(org_id=world.a.org_id, user_id=user["id"], name="h")["token"]
    not_owner = {"Authorization": f"Bearer {helper}"}
    refused = c.delete("/api/v1/org", params={"confirm": "Alpha Capital"}, headers=not_owner)
    assert refused.status_code == 403  # an admin who is not an owner cannot delete the organisation
    r = c.delete("/api/v1/org", params={"confirm": "Alpha Capital"}, headers=world.a.h)
    assert r.status_code == 204
    assert c.get("/api/v1/me", headers=world.a.h).status_code == 401  # tokens die at once
    assert c.get("/api/v1/me", headers=world.b.h).status_code == 200  # others unaffected
    assert _count(world, CaseRow) == 1  # still held during the grace period

    life = c.app.state.container.lifecycle  # type: ignore[attr-defined]
    removed = life.purge_org(world.a.org_id, actor="cli")
    assert removed["share_links"] == 1  # the link made by the shared fixture
    assert removed["cases"] == 1 and removed["documents"] == 1
    assert _count(world, CaseRow) == 0
    assert _count(world, OrganisationRow, OrganisationRow.id == world.a.org_id) == 0
    assert _count(world, ApiTokenRow, ApiTokenRow.org_id == world.a.org_id) == 0
    assert _count(world, AuditEventRow, AuditEventRow.action == "org.purged") == 1


def test_purge_requires_a_prior_deletion(world: World) -> None:
    life = world.client.app.state.container.lifecycle  # type: ignore[attr-defined]
    with pytest.raises(Exception, match="Delete the organisation first"):
        life.purge_org(world.a.org_id, actor="t")
    assert _count(world, CaseRow) == 1


def test_a_failure_inside_the_lifted_section_leaves_the_protection_in_place(world: World) -> None:
    """The DROP TRIGGER must be part of the transaction, so a rollback puts the triggers back.

    pysqlite only opens a transaction before an INSERT/UPDATE/DELETE, so a DROP TRIGGER run
    after a plain SELECT used to commit by itself and a later failure left it dropped for good.
    """
    from ipo_engine.screening.db.maintenance import append_only_lifted

    db = world.client.app.state.container.db  # type: ignore[attr-defined]

    def triggers() -> set[str]:
        with db.engine.connect() as conn:
            rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'"))
            return {r[0] for r in rows}

    before = triggers()
    assert len(before) >= 8
    for opener in ("select", "delete", "nothing"):
        with pytest.raises(RuntimeError, match="boom"), db.session() as s:
            if opener == "select":
                s.execute(text("SELECT 1"))
            elif opener == "delete":
                s.execute(text("DELETE FROM case_data_versions WHERE 1 = 0"))
            with append_only_lifted(s):
                # a DML statement inside the section is what opens pysqlite's own transaction
                s.execute(text("DELETE FROM review_item_events WHERE 1 = 0"))
                raise RuntimeError("boom")
        assert triggers() == before, f"triggers lost after a failure that began with {opener!r}"
