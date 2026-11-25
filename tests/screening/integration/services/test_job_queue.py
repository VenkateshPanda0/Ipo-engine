"""The shared document queue and shared rate limits: exclusive claims, leases, workers, limits."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.screening.conftest import PG_ADMIN_URL, _drop_postgres_databases, _new_postgres_database
from tests.screening.fixtures.pdf_factory import standard_drhp
from tests.screening.integration.api.accounts_world import build_world

from ipo_engine.screening.api.dependencies import Container
from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.db.models import DocumentRow
from ipo_engine.screening.main import create_app
from ipo_engine.screening.services.documents import DbRateLimiter, RateLimiter

ANALYST = {"Authorization": "Bearer k"}


@pytest.fixture
def make_site(tmp_path: Path) -> Iterator[Callable[..., tuple[TestClient, Settings]]]:
    """Apps that share one database and data directory, with real (not inline) job handling."""
    created: list[str] = []
    clients: list[TestClient] = []
    url = _new_postgres_database(created) if PG_ADMIN_URL else f"sqlite:///{tmp_path / 'q.db'}"

    def make(**env: Any) -> tuple[TestClient, Settings]:
        values = {
            "DATA_DIR": str(tmp_path / "data"),
            "DATABASE_URL": url,
            "API_KEYS": "ann|analyst|k",
            **{k: str(v) for k, v in env.items()},
        }
        settings = Settings(**values)  # type: ignore[arg-type]
        client = TestClient(create_app(settings, inline_processing=False))
        client.__enter__()
        clients.append(client)
        return client, settings

    yield make
    for c in clients:
        c.__exit__(None, None, None)
    _drop_postgres_databases(created)


def _upload(client: TestClient, name: str = "Acme Ltd") -> tuple[str, str]:
    case = client.post("/api/v1/cases", json={"company_name": name}, headers=ANALYST).json()
    doc = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files={"file": ("d.pdf", standard_drhp() + name.encode(), "application/pdf")},
        headers=ANALYST,
    )
    assert doc.status_code == 202, doc.text
    return case["id"], doc.json()["id"]


def _status(client: TestClient, doc_id: str) -> str:
    return str(client.get(f"/api/v1/documents/{doc_id}", headers=ANALYST).json()["status"])


def _wait(client: TestClient, doc_id: str, want: set[str], seconds: float = 40) -> str:
    end = time.time() + seconds
    while time.time() < end:
        status = _status(client, doc_id)
        if status in want:
            return status
        time.sleep(0.2)
    raise AssertionError(f"document stayed {status!r}, wanted {want}")


def test_in_queue_mode_an_upload_waits_until_some_worker_claims_it(
    make_site: Callable[..., tuple[TestClient, Settings]],
) -> None:
    api, settings = make_site(JOB_MODE="queue", WORKER_THREADS="0")  # an API process, no workers
    _, doc_id = _upload(api)
    time.sleep(0.5)
    assert _status(api, doc_id) == "uploaded"  # nothing processes it here

    other = Container.build(settings)  # a different process on the same database
    claimed = other.documents.claim_next("worker-b")
    assert claimed == doc_id
    assert other.documents.claim_next("worker-c") is None  # taken: nobody else can have it
    other.documents.process(doc_id, worker="worker-b", claimed=True)
    assert _status(api, doc_id) in {"awaiting_review", "completed"}
    other.shutdown()


def test_workers_inside_the_api_process_drain_the_queue(
    make_site: Callable[..., tuple[TestClient, Settings]],
) -> None:
    api, _ = make_site(JOB_MODE="queue", WORKER_THREADS="2")
    docs = [_upload(api, f"Co {n} Ltd")[1] for n in range(3)]
    for d in docs:
        assert _wait(api, d, {"awaiting_review", "completed"})


def test_many_racing_workers_never_take_the_same_job_twice(
    make_site: Callable[..., tuple[TestClient, Settings]],
) -> None:
    api, settings = make_site(JOB_MODE="queue", WORKER_THREADS="0")
    ids = {_upload(api, f"Race {n} Ltd")[1] for n in range(6)}
    boxes = [Container.build(settings) for _ in range(4)]
    got: list[str] = []
    lock = threading.Lock()

    def grab(box: Container, who: str) -> None:
        while (job := box.documents.claim_next(who)) is not None:
            with lock:
                got.append(job)

    threads = [threading.Thread(target=grab, args=(b, f"w{i}")) for i, b in enumerate(boxes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(got) == sorted(ids)  # every job exactly once
    for b in boxes:
        b.shutdown()


def test_a_dead_worker_loses_its_job_after_the_lease_and_it_is_retried(
    make_site: Callable[..., tuple[TestClient, Settings]],
) -> None:
    api, settings = make_site(JOB_MODE="queue", WORKER_THREADS="0", JOB_MAX_ATTEMPTS="2")
    _, doc_id = _upload(api)
    box = Container.build(settings)
    docs = box.documents

    def expire() -> None:
        from datetime import UTC, datetime, timedelta

        with box.db.session() as s:
            row = s.get(DocumentRow, doc_id)
            assert row is not None
            row.lease_expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)

    assert docs.claim_next("dies-1") == doc_id  # attempt 1, then the worker vanishes
    assert docs.requeue_expired() == (0, 0)  # lease still running: leave it alone
    expire()
    assert docs.requeue_expired() == (1, 0)
    assert _status(api, doc_id) == "uploaded"
    assert docs.claim_next("dies-2") == doc_id  # attempt 2
    expire()
    assert docs.requeue_expired() == (0, 1)  # out of attempts: failed, not looping
    info = api.get(f"/api/v1/documents/{doc_id}", headers=ANALYST).json()
    assert info["status"] == "failed" and info["error_code"] == "INTERRUPTED"
    box.shutdown()


def test_starting_a_second_process_does_not_fail_jobs_that_are_running_elsewhere(
    make_site: Callable[..., tuple[TestClient, Settings]],
) -> None:
    api, settings = make_site(JOB_MODE="queue", WORKER_THREADS="0")
    _, doc_id = _upload(api)
    busy = Container.build(settings)
    assert busy.documents.claim_next("busy") == doc_id  # mid-job, lease fresh
    second, _ = make_site(JOB_MODE="queue", WORKER_THREADS="0")  # starts up, runs startup()
    assert _status(second, doc_id) == "extracting"
    with busy.db.session() as s:
        row = s.execute(select(DocumentRow).where(DocumentRow.id == doc_id)).scalar_one()
        assert row.claimed_by == "busy"
    busy.shutdown()


def test_local_mode_is_unchanged_a_restart_marks_unfinished_documents_failed(
    make_site: Callable[..., tuple[TestClient, Settings]],
) -> None:
    api, settings = make_site()
    _, doc_id = _upload(api)
    _wait(api, doc_id, {"awaiting_review", "completed"})
    box = Container.build(settings)
    with box.db.session() as s:  # as if the process had died mid-extraction
        row = s.get(DocumentRow, doc_id)
        assert row is not None
        row.status = "extracting"
    box.shutdown()
    restarted, _ = make_site()
    info = restarted.get(f"/api/v1/documents/{doc_id}", headers=ANALYST).json()
    assert info["status"] == "failed" and info["error_code"] == "INTERRUPTED"


# ------------------------------------------------------------------- rate limits
def test_the_database_limiter_is_one_limit_across_processes(
    make_site: Callable[..., tuple[TestClient, Settings]],
) -> None:
    api, settings = make_site()
    box_a, box_b = Container.build(settings), Container.build(settings)
    a, b = DbRateLimiter(box_a.db, 3), DbRateLimiter(box_b.db, 3)
    assert [a.allow("u"), b.allow("u"), a.allow("u"), b.allow("u")] == [True, True, True, False]
    assert a.allow("someone-else")  # keys are independent
    assert api
    box_a.shutdown()
    box_b.shutdown()


def test_the_memory_limiter_is_per_process_by_contrast() -> None:
    a, b = RateLimiter(2), RateLimiter(2)
    assert [a.allow("u"), a.allow("u"), a.allow("u")] == [True, True, False]
    assert b.allow("u")  # another process knows nothing of a's count


def test_the_window_slides(make_site: Callable[..., tuple[TestClient, Settings]]) -> None:
    _, settings = make_site()
    box = Container.build(settings)
    limiter = DbRateLimiter(box.db, 1)
    assert limiter.allow("k") and not limiter.allow("k")
    from datetime import UTC, datetime, timedelta

    from ipo_engine.screening.db.models import RateHitRow

    with box.db.session() as s:
        for hit in s.execute(select(RateHitRow)).scalars():
            hit.ts = datetime.now(tz=UTC) - timedelta(seconds=61)
    assert limiter.allow("k")  # the old hit no longer counts
    with box.db.session() as s2:  # age the new hit too, then sweep
        for hit in s2.execute(select(RateHitRow)).scalars():
            hit.ts = datetime.now(tz=UTC) - timedelta(seconds=61)
    assert limiter.sweep() >= 1  # housekeeping removes what has aged out
    box.shutdown()


def test_api_requests_are_limited_per_user(app_factory: Any) -> None:
    w = build_world(app_factory, seed_a=False, API_RATE_LIMIT_PER_MINUTE="4")
    codes = [w.client.get("/api/v1/me", headers=w.a.h).status_code for _ in range(6)]
    assert codes == [200, 200, 200, 200, 429, 429]
    limited = w.client.get("/api/v1/me", headers=w.a.h)
    assert limited.headers["retry-after"] == "60"
    assert w.client.get("/api/v1/me", headers=w.b.h).status_code == 200  # others are unaffected


def test_the_limit_can_live_in_the_shared_database(app_factory: Any) -> None:
    w = build_world(
        app_factory, seed_a=False, API_RATE_LIMIT_PER_MINUTE="2", RATE_LIMIT_STORE="database"
    )
    codes = [w.client.get("/api/v1/me", headers=w.a.h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
