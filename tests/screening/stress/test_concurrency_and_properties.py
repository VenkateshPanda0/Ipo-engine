"""Intensive checks: thread races, properties over arbitrary input, and an isolation fuzz."""

from __future__ import annotations

import io
import random
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ipo_engine.screening.core.security import Role
from ipo_engine.screening.network.http import HttpError
from ipo_engine.screening.network.webhook_http import validate_target
from ipo_engine.screening.services.documents import DbRateLimiter
from ipo_engine.screening.services.signin import safe_next
from ipo_engine.screening.services.tabular import cell_text, to_csv, to_xlsx
from ipo_engine.screening.services.webhooks import sign, verify_signature
from tests.screening.integration.api.accounts_world import World, build_world, make_member

ROOT = Path(__file__).resolve().parents[3]


# ------------------------------------------------------------------- properties
@given(st.text())
def test_a_spreadsheet_cell_never_starts_with_anything_executable(text: str) -> None:
    out = cell_text(text)
    assert not out.startswith(("=", "+", "-", "@", "\t", "\r"))
    assert out.lstrip("'") == text.lstrip("'") or out == "'" + text


@given(st.lists(st.lists(st.text(), min_size=1, max_size=4), max_size=6))
@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
def test_any_text_makes_a_valid_workbook_and_a_readable_csv(rows: list[list[str]]) -> None:
    raw = to_xlsx("S", ["a", "b", "c", "d"], rows)
    z = zipfile.ZipFile(io.BytesIO(raw))
    for name in z.namelist():
        ElementTree.fromstring(z.read(name))
    csv_bytes = to_csv(["a", "b", "c", "d"], rows)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")


@given(st.text(max_size=300))
def test_the_return_address_is_always_a_path_on_this_site(value: str) -> None:
    out = safe_next(value)
    assert out.startswith("/") and not out.startswith("//") and "\\" not in out
    assert not any(ord(c) < 32 for c in out)


@given(st.binary(max_size=200), st.text(min_size=1, max_size=40), st.integers(0, 2**31))
def test_a_signature_verifies_only_for_the_exact_body_secret_and_time(
    body: bytes, secret: str, ts: int
) -> None:
    header = sign(secret, ts, body)
    assert header.startswith(f"t={ts},v1=") and len(header.split("v1=")[1]) == 64
    assert sign(secret, ts, body + b"x") != header
    assert sign(secret + "x", ts, body) != header
    assert sign(secret, ts + 1, body) != header
    assert (
        not verify_signature(secret, header, body, tolerance_s=300)
        or abs(ts - __import__("time").time()) <= 300
    )


@given(st.ip_addresses(v=4))
def test_no_non_public_ipv4_literal_is_accepted_as_a_webhook_target(ip: Any) -> None:
    if ip.is_global:
        validate_target(f"https://{ip}/x")
    else:
        with pytest.raises(HttpError):
            validate_target(f"https://{ip}/x")


@given(st.ip_addresses(v=6))
def test_no_non_public_ipv6_literal_is_accepted_as_a_webhook_target(ip: Any) -> None:
    if ip.is_global:
        validate_target(f"https://[{ip}]/x")
    else:
        with pytest.raises(HttpError):
            validate_target(f"https://[{ip}]/x")


# ---------------------------------------------------------------------- races
@pytest.fixture
def world(app_factory: Any) -> World:
    return build_world(app_factory)


def _clients(w: World, n: int) -> list[TestClient]:
    return [TestClient(w.client.app) for _ in range(n)]


def test_many_threads_commenting_at_once_lose_nothing(world: World) -> None:
    clients = _clients(world, 8)
    errors: list[int] = []

    def go(c: TestClient, who: int) -> None:
        for n in range(5):
            r = c.post(
                f"/api/v1/cases/{world.case_a}/comments",
                json={"body": f"t{who}-{n}"},
                headers=world.a.h,
            )
            if r.status_code != 201:
                errors.append(r.status_code)

    threads = [threading.Thread(target=go, args=(c, i)) for i, c in enumerate(clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert errors == []
    bodies = [
        c["body"]
        for c in world.client.get(
            f"/api/v1/cases/{world.case_a}/comments", headers=world.a.h
        ).json()
    ]
    assert len(bodies) == 1 + 8 * 5 and len(set(bodies)) == len(bodies)


def test_once_a_member_is_removed_no_later_request_with_their_token_succeeds(world: World) -> None:
    victim = make_member(world.client, world.a.org_id, "gone@alpha.example", Role.ANALYST)
    clients = _clients(world, 6)
    removed = threading.Event()
    after_removal_ok: list[int] = []
    stop = threading.Event()

    def hammer(c: TestClient) -> None:
        while not stop.is_set():
            was_removed = removed.is_set()  # read BEFORE asking: removal had finished by then
            code = c.get("/api/v1/cases", headers=victim.h).status_code
            if was_removed and code == 200:
                after_removal_ok.append(code)

    threads = [threading.Thread(target=hammer, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    r = world.client.delete(f"/api/v1/org/members/{victim.user_id}", headers=world.a.h)
    assert r.status_code == 204
    removed.set()
    threading.Event().wait(0.5)
    stop.set()
    for t in threads:
        t.join(30)
    assert after_removal_ok == []


def test_two_organisations_working_at_once_never_see_each_other(world: World) -> None:
    clients = _clients(world, 6)
    leaks: list[str] = []

    def work(c: TestClient, member: Any, tag: str, other: str) -> None:
        for n in range(6):
            c.post("/api/v1/cases", json={"company_name": f"{tag} {n}"}, headers=member.h)
            listing = c.get("/api/v1/cases?limit=200", headers=member.h).json()["items"]
            leaks.extend(i["company_name"] for i in listing if i["company_name"].startswith(other))
            csv = c.get("/api/v1/exports/cases", headers=member.h).text
            if other in csv:
                leaks.append("csv:" + other)

    threads = []
    for i, c in enumerate(clients):
        member, tag, other = (
            (world.a, "AlphaWork", "BetaWork") if i % 2 == 0 else (world.b, "BetaWork", "AlphaWork")
        )
        threads.append(threading.Thread(target=work, args=(c, member, tag, other)))
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert leaks == []


def test_the_shared_rate_limit_stays_within_limit_plus_concurrency(world: World) -> None:
    db = world.client.app.state.container.db  # type: ignore[attr-defined]
    limiter = DbRateLimiter(db, 5)
    allowed: list[bool] = []
    threads = [
        threading.Thread(target=lambda: allowed.append(limiter.allow("k"))) for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert (
        5 <= sum(allowed) <= 8
    )  # documented: may exceed by at most the callers racing at that instant
    assert not limiter.allow("k")  # and the window is full afterwards


# ------------------------------------------------------------- isolation fuzz
def test_random_work_in_two_organisations_never_crosses_over(world: World) -> None:
    """200 random calls; no answer to one organisation ever holds the other's marker."""
    rnd = random.Random(20261125)
    c = world.client
    ana = make_member(c, world.a.org_id, "ana@alpha.example", Role.ANALYST)
    bea = make_member(c, world.b.org_id, "bea@beta.example", Role.ANALYST)
    marker = {world.a.org_id: "ALPHA-MARK", world.b.org_id: "BETA-MARK"}
    people = [world.a, ana, world.b, bea]
    mine: dict[str, list[str]] = {world.a.org_id: [world.case_a], world.b.org_id: []}
    c.post("/api/v1/cases", json={"company_name": "BETA-MARK seed"}, headers=world.b.h)
    mine[world.b.org_id].append(c.get("/api/v1/cases", headers=world.b.h).json()["items"][0]["id"])
    seen: list[tuple[str, str]] = []

    def check(p: Any, resp: Any) -> None:
        other = marker[world.b.org_id if p.org_id == world.a.org_id else world.a.org_id]
        if other in resp.text:
            seen.append((p.user_id, f"{resp.request.method} {resp.request.url.path}"))

    for _ in range(200):
        p = rnd.choice(people)
        m = marker[p.org_id]
        pick = rnd.randrange(9)
        cid = rnd.choice(mine[p.org_id])
        if pick == 0:
            r = c.post(
                "/api/v1/cases", json={"company_name": f"{m} {rnd.randrange(1000)}"}, headers=p.h
            )
            if r.status_code == 201:
                mine[p.org_id].append(r.json()["id"])
        elif pick == 1:
            r = c.post(f"/api/v1/cases/{cid}/comments", json={"body": f"{m} note"}, headers=p.h)
        elif pick == 2:
            r = c.get("/api/v1/cases", headers=p.h)
        elif pick == 3:
            r = c.get("/api/v1/dashboard", headers=p.h)
        elif pick == 4:
            r = c.get(f"/api/v1/cases/{cid}/comments", headers=p.h)
        elif pick == 5:
            r = c.get("/api/v1/exports/cases", headers=p.h)
        elif pick == 6:
            r = c.get("/api/v1/reports", headers=p.h)
        elif pick == 7:
            # an id from the OTHER organisation: must be a 404, and must say nothing about it
            foreign = rnd.choice(
                mine[world.b.org_id if p.org_id == world.a.org_id else world.a.org_id]
            )
            r = c.get(f"/api/v1/cases/{foreign}", headers=p.h)
            assert r.status_code == 404
        else:
            r = c.get("/api/v1/notifications", headers=p.h)
        check(p, r)
    assert seen == []


# ------------------------------------------------------------ the load tool
def test_the_load_tool_runs_clean_against_a_throwaway_server() -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "loadtest.py"), "--selfhost", "--duration", "4"],
        capture_output=True, text=True, timeout=180, cwd=ROOT,
    )  # fmt: skip
    assert out.returncode == 0, out.stdout + out.stderr
    assert "leaks: 0   unexpected responses: 0" in out.stdout
    assert "p95 ms" in out.stdout and "requests/second" in out.stdout


def test_many_first_sign_ins_for_one_new_email_all_succeed(tmp_path: Path) -> None:
    """Concurrent first requests for the same person must all get that one user, not a 500."""
    import threading

    from ipo_engine.screening.db.base import Database
    from ipo_engine.screening.services.accounts import AccountService

    db = Database(f"sqlite:///{tmp_path}/race.db")
    db.migrate()
    accounts = AccountService(db)
    out: list[Any] = []
    gate = threading.Barrier(8)

    def go() -> None:
        gate.wait()
        try:
            out.append(accounts.get_or_create_user("new.person@race.example")["id"])
        except Exception as exc:  # the failure this test exists to catch
            out.append(exc)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(isinstance(x, str) for x in out), out
    assert len(set(out)) == 1
