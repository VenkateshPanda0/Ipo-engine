"""S3-compatible document storage: the signer against AWS's published vector, and the app on it."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.screening.fixtures.pdf_factory import standard_drhp

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.main import create_app
from ipo_engine.screening.network.s3 import S3Store, StorageError, sign_v4


def test_the_signer_matches_the_aws_published_get_vanilla_vector() -> None:
    """From the AWS Signature Version 4 test suite ("get-vanilla")."""
    auth = sign_v4(
        method="GET", host="example.amazonaws.com", path="/", query="",
        headers={"X-Amz-Date": "20150830T123600Z"},
        payload_sha256=hashlib.sha256(b"").hexdigest(),
        access_key="AKIDEXAMPLE", secret_key="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        region="us-east-1", service="service", amz_date="20150830T123600Z",
    )  # fmt: skip
    assert auth == (
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
        "SignedHeaders=host;x-amz-date, "
        "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"
    )


class FakeS3:
    """An in-memory bucket that checks what a real one checks: a signature of the request it got."""

    def __init__(self, access: str, secret: str, region: str) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str]] = []
        self._access, self._secret, self._region = access, secret, region

    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, bytes]:
        m = re.match(r"https?://([^/]+)(/.*)$", url)
        assert m, url
        host, path = m.groups()
        self.calls.append((method, path))
        assert headers["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()
        signed = {k: v for k, v in headers.items() if k in ("x-amz-content-sha256", "x-amz-date")}
        expected = sign_v4(
            method=method, host=host, path=path, query="", headers=signed,
            payload_sha256=headers["x-amz-content-sha256"], access_key=self._access,
            secret_key=self._secret, region=self._region, service="s3",
            amz_date=headers["x-amz-date"],
        )  # fmt: skip
        if headers.get("Authorization") != expected:
            return 403, b"SignatureDoesNotMatch"
        if method == "PUT":
            self.objects[path] = body
            return 200, b""
        if method == "GET":
            return (200, self.objects[path]) if path in self.objects else (404, b"")
        if method == "HEAD":
            return (200, b"") if path in self.objects else (404, b"")
        if method == "DELETE":
            self.objects.pop(path, None)
            return 204, b""
        return 405, b""


def _store(fake: FakeS3, **kw: Any) -> S3Store:
    return S3Store(
        bucket="docs", region="ap-south-1", access_key="AK", secret_key="SK", transport=fake,
        clock=lambda: dt.datetime(2026, 11, 25, 12, 0, 0, tzinfo=dt.UTC), **kw,
    )  # fmt: skip


SHA = hashlib.sha256(b"pdf").hexdigest()


def test_put_get_exists_delete_round_trip_with_a_signed_request() -> None:
    fake = FakeS3("AK", "SK", "ap-south-1")
    s = _store(fake)
    assert not s.exists(SHA) and s.get(SHA) is None and s.delete(SHA) is False
    assert s.put(SHA, b"%PDF-1.4 x") == f"{SHA}.pdf"
    assert s.exists(SHA) and s.get(SHA) == b"%PDF-1.4 x"
    assert [m for m, _ in fake.calls].count("PUT") == 1
    s.put(SHA, b"%PDF-1.4 x")  # content-addressed: the second upload is a no-op
    assert [m for m, _ in fake.calls].count("PUT") == 1
    assert s.delete(SHA) is True and not s.exists(SHA)


def test_a_wrong_secret_is_refused_by_the_store_and_reported() -> None:
    fake = FakeS3("AK", "RIGHT", "ap-south-1")
    bad = S3Store(
        bucket="docs", region="ap-south-1", access_key="AK", secret_key="WRONG", transport=fake
    )
    with pytest.raises(StorageError, match="403"):
        bad.exists(SHA)


def test_virtual_hosted_and_path_style_urls_and_prefix() -> None:
    seen: list[str] = []

    class Spy:
        def request(
            self, method: str, url: str, headers: dict[str, str], body: bytes
        ) -> tuple[int, bytes]:
            seen.append(url)
            return 404, b""

    S3Store(bucket="b", region="eu-west-1", access_key="a", secret_key="s", transport=Spy()).exists(
        SHA
    )
    S3Store(
        bucket="b", region="x", access_key="a", secret_key="s", endpoint="http://minio:9000",
        prefix="/tenant-1/", transport=Spy(),
    ).exists(SHA)  # fmt: skip
    assert seen[0] == f"https://b.s3.eu-west-1.amazonaws.com/documents/{SHA}.pdf"
    assert seen[1] == f"http://minio:9000/b/tenant-1/documents/{SHA}.pdf"


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "A" * 64, "g" * 64, SHA[:-1]])
def test_a_digest_that_is_not_hex_never_reaches_a_key(bad: str) -> None:
    s = _store(FakeS3("AK", "SK", "ap-south-1"))
    with pytest.raises(ValueError, match="digest"):
        s.put(bad, b"x")


def test_missing_credentials_are_refused_up_front() -> None:
    with pytest.raises(StorageError, match="S3_BUCKET"):
        S3Store(bucket="", region="r", access_key="", secret_key="")


def test_the_whole_app_runs_on_a_bucket(tmp_path: Any) -> None:
    fake = FakeS3("AK", "SK", "ap-south-1")
    s = Settings(
        DATA_DIR=str(tmp_path / "d"), DATABASE_URL=f"sqlite:///{tmp_path / 'a.db'}",
        API_KEYS="ann|admin|k", STORAGE_BACKEND="s3", S3_BUCKET="docs", S3_REGION="ap-south-1",
        S3_ACCESS_KEY_ID="AK", S3_SECRET_ACCESS_KEY="SK",
    )  # fmt: skip
    h = {"Authorization": "Bearer k"}
    with TestClient(create_app(s, inline_processing=True, s3_transport=fake)) as c:
        case = c.post("/api/v1/cases", json={"company_name": "Bucket Ltd"}, headers=h).json()
        doc = c.post(
            f"/api/v1/cases/{case['id']}/documents",
            files={"file": ("d.pdf", standard_drhp(), "application/pdf")},
            headers=h,
        ).json()
        assert doc["id"] and len(fake.objects) == 1  # the PDF is in the bucket, not on disk
        assert not list((tmp_path / "d").rglob("*.pdf"))
        got = c.get(f"/api/v1/documents/{doc['id']}/content", headers=h)
        assert got.status_code == 200 and got.content.startswith(b"%PDF")
        assert c.get(f"/api/v1/documents/{doc['id']}", headers=h).json()["status"] in (
            "awaiting_review", "completed",
        )  # fmt: skip
        erased = c.delete(
            f"/api/v1/cases/{case['id']}", params={"confirm": "Bucket Ltd"}, headers=h
        )
        assert erased.status_code == 200 and fake.objects == {}  # erasure removed the object
