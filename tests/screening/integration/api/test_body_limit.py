"""Oversized request bodies are refused before they are read into memory."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from tests.screening.fixtures.pdf_factory import standard_drhp

H = {"Authorization": "Bearer k", "Content-Type": "application/json"}


@pytest.fixture
def client(app_factory: Any) -> Any:
    return app_factory(API_KEYS="ann|admin|k", MAX_JSON_BODY_MB="1")


def test_a_declared_oversized_body_is_refused_at_once_with_the_usual_protections(
    client: Any,
) -> None:
    body = json.dumps({"company_name": "x" * (3 * 1024 * 1024)})
    r = client.post("/api/v1/cases", content=body, headers=H)
    assert r.status_code == 413
    assert (
        r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE" and "1 MB" in r.json()["error"]["message"]
    )
    assert r.headers["x-request-id"] and r.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in r.headers["cache-control"]


def test_a_chunked_body_is_cut_off_when_it_passes_the_limit(client: Any) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"company_name": "'
        for _ in range(40):  # no Content-Length: 40 x 100 KB
            yield b"y" * 100_000
        yield b'"}'

    r = client.post("/api/v1/cases", content=chunks(), headers=H)
    assert r.status_code == 413


@pytest.mark.parametrize("method", ["post", "put", "patch"])
def test_every_method_that_carries_a_body_is_limited(client: Any, method: str) -> None:
    big = b'{"x": "' + b"z" * (2 * 1024 * 1024) + b'"}'
    r = getattr(client, method)("/api/v1/cases", content=big, headers=H)
    assert r.status_code == 413  # (even where the route would have said 405: no body is read first)


def test_ordinary_bodies_and_the_limit_boundary_still_work(client: Any) -> None:
    ok = client.post("/api/v1/cases", json={"company_name": "Fine Ltd"}, headers=H)
    assert ok.status_code == 201
    comment = {"body": "c" * 5000}  # the largest comment the API accepts is far below the limit
    assert client.post(
        f"/api/v1/cases/{ok.json()['id']}/comments", json=comment, headers=H
    ).status_code in (201, 404)
    small = json.dumps({"company_name": "a" * 250}).encode()
    assert client.post("/api/v1/cases", content=small, headers=H).status_code == 201


def test_get_requests_and_uploads_are_not_subject_to_the_json_limit(client: Any) -> None:
    case = client.post("/api/v1/cases", json={"company_name": "Upload Ltd"}, headers=H).json()
    pdf = standard_drhp()
    assert len(pdf) < 1024 * 1024
    r = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files={"file": ("d.pdf", pdf + b"%" * (1024 * 1024 + 10), "application/pdf")},
        headers={"Authorization": "Bearer k"},
    )
    assert (
        r.status_code != 413
    )  # a multipart upload is governed by MAX_UPLOAD_SIZE_MB, not this limit
    assert client.get("/api/v1/cases", headers=H).status_code == 200


def test_the_default_limit_is_two_megabytes(app_factory: Any) -> None:
    c = app_factory(API_KEYS="ann|admin|k")
    just_under = json.dumps({"company_name": "a" * (1024 * 1024)}).encode()
    assert c.post("/api/v1/cases", content=just_under, headers=H).status_code in (201, 422)
    over = json.dumps({"company_name": "a" * (2 * 1024 * 1024 + 10)}).encode()
    assert c.post("/api/v1/cases", content=over, headers=H).status_code == 413
