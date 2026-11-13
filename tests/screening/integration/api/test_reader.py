"""The reader's brief through the API (synthetic PDF, inline processing)."""

from __future__ import annotations

from typing import Any

from tests.screening.fixtures.pdf_factory import standard_drhp
from tests.screening.integration.api.test_v1_workflow import (
    ANALYST,
    VIEWER,
    _case,
    _client,
    _upload,
)


def test_reader_brief_is_started_once_cached_and_cites_pages(app_factory: Any) -> None:
    client = _client(app_factory)
    doc = _upload(client, _case(client)["id"], standard_drhp())
    url = f"/api/v1/documents/{doc['id']}/reader"

    before = client.get(url, headers=VIEWER).json()
    assert before["status"] == "not_started" and before["brief"] is None

    assert client.post(url, headers=VIEWER).status_code == 403  # a viewer cannot start work
    started = client.post(url, headers=ANALYST)
    assert started.status_code == 202, started.text

    ready = client.get(url, headers=VIEWER).json()
    assert ready["status"] == "ready"
    brief = ready["brief"]
    assert brief["pages"] >= 1
    assert set(brief) >= {"issue", "metrics", "read_first", "rules_checked", "numbers_verified"}
    verified, total = brief["numbers_verified"]
    assert verified <= total
    for item in brief["read_first"]:
        assert item["kind"] and item["text"]
    # asking again does not run the reader a second time: same cached result
    assert client.post(url, headers=ANALYST).json()["brief"] == brief


def test_reader_on_a_deleted_file_is_refused(app_factory: Any) -> None:
    client = _client(app_factory)
    doc = _upload(client, _case(client)["id"], standard_drhp())
    admin = {"Authorization": "Bearer admin-key"}
    assert client.delete(f"/api/v1/documents/{doc['id']}/content", headers=admin).status_code == 200
    r = client.post(f"/api/v1/documents/{doc['id']}/reader", headers=ANALYST)
    assert r.status_code == 409, r.text


def test_reader_for_an_unknown_document_is_404(app_factory: Any) -> None:
    client = _client(app_factory)
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/documents/{missing}/reader", headers=VIEWER).status_code == 404
