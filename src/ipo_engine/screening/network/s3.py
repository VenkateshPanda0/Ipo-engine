"""
Object storage for uploaded documents, speaking the S3 protocol (AWS S3, MinIO, Cloudflare R2, ...).

A small SigV4 signer and four calls (PUT, GET, HEAD, DELETE) over the standard library, so the
service has no cloud SDK to patch or audit. Keys are ``<prefix>documents/<sha256>.pdf``; the digest
is validated before it is ever put in a key. Objects are content-addressed, so a repeated upload is
a no-op, exactly as with the local store.

Use it by setting ``STORAGE_BACKEND=s3`` and the ``S3_*`` variables (docs/OPERATIONS.md).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import http.client
import re
import urllib.parse
from collections.abc import Callable
from typing import Protocol

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
TIMEOUT_S = 30.0
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class StorageError(RuntimeError):
    """The object store could not be reached or refused the request."""


class Transport(Protocol):
    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, bytes]: ...


class HttpTransport:
    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, bytes]:
        parts = urllib.parse.urlsplit(url)
        cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        conn = cls(parts.netloc, timeout=TIMEOUT_S)
        try:
            target = parts.path + (f"?{parts.query}" if parts.query else "")
            conn.request(method, target, body=body or None, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read()
        except (OSError, http.client.HTTPException) as exc:
            raise StorageError(f"object store unreachable: {type(exc).__name__}") from exc
        finally:
            conn.close()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign_v4(
    *,
    method: str,
    host: str,
    path: str,
    query: str,
    headers: dict[str, str],
    payload_sha256: str,
    access_key: str,
    secret_key: str,
    region: str,
    service: str,
    amz_date: str,
) -> str:
    """The ``Authorization`` header value for a request (AWS Signature Version 4).

    ``headers`` are the headers to sign besides ``host`` (which is added), lower-cased names.
    """
    signed = {k.lower(): " ".join(v.split()) for k, v in headers.items()}
    signed["host"] = host
    names = sorted(signed)
    canonical = "\n".join(
        [
            method,
            urllib.parse.quote(path, safe="/-_.~"),
            query,
            "".join(f"{n}:{signed[n]}\n" for n in names),
            ";".join(names),
            payload_sha256,
        ]
    )
    day = amz_date[:8]
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = _hmac(
        _hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), day), region), service), "aws4_request"
    )
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={';'.join(names)}, Signature={signature}"
    )


class S3Store:
    """The same interface as ``FileStore``, backed by a bucket."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        endpoint: str | None = None,
        prefix: str = "",
        transport: Transport | None = None,
        clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    ) -> None:
        if not bucket or not access_key or not secret_key:
            raise StorageError("S3 needs S3_BUCKET, S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY.")
        self._bucket, self._region = bucket, region
        self._access, self._secret = access_key, secret_key
        self._endpoint = endpoint.rstrip("/") if endpoint else None
        self._prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self._transport = transport or HttpTransport()
        self._clock = clock

    def _key(self, sha256: str) -> str:
        if not _HEX64.match(sha256):
            raise ValueError("invalid document digest")
        return f"{self._prefix}documents/{sha256}.pdf"

    def _call(self, method: str, key: str, body: bytes = b"") -> tuple[int, bytes]:
        if self._endpoint:  # path style: MinIO and most compatible stores
            base = urllib.parse.urlsplit(self._endpoint)
            host, path = base.netloc, f"{base.path.rstrip('/')}/{self._bucket}/{key}"
            scheme = base.scheme
        else:  # AWS virtual-hosted style
            host, path, scheme = (
                f"{self._bucket}.s3.{self._region}.amazonaws.com",
                f"/{key}",
                "https",
            )
        now = self._clock()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        payload = hashlib.sha256(body).hexdigest()
        headers = {"x-amz-content-sha256": payload, "x-amz-date": amz_date}
        headers["Authorization"] = sign_v4(
            method=method, host=host, path=path, query="", headers=headers, payload_sha256=payload,
            access_key=self._access, secret_key=self._secret, region=self._region, service="s3",
            amz_date=amz_date,
        )  # fmt: skip
        url = f"{scheme}://{host}{urllib.parse.quote(path, safe='/-_.~')}"
        return self._transport.request(method, url, {**headers, "Host": host}, body)

    # --- the FileStore interface ---------------------------------------------------
    def put(self, sha256: str, content: bytes) -> str:
        key = self._key(sha256)
        if not self.exists(sha256):
            status, _ = self._call("PUT", key, content)
            if status not in (200, 201, 204):
                raise StorageError(f"object store refused the upload ({status})")
        return f"{sha256}.pdf"

    def get(self, sha256: str) -> bytes | None:
        status, body = self._call("GET", self._key(sha256))
        if status == 404:
            return None
        if status != 200:
            raise StorageError(f"object store answered {status}")
        return body

    def exists(self, sha256: str) -> bool:
        status, _ = self._call("HEAD", self._key(sha256))
        if status == 404:
            return False
        if status != 200:
            raise StorageError(f"object store answered {status}")
        return True

    def delete(self, sha256: str) -> bool:
        key = self._key(sha256)
        existed = self.exists(sha256)
        if existed:
            status, _ = self._call("DELETE", key)
            if status not in (200, 204):
                raise StorageError(f"object store refused the delete ({status})")
        return existed

    def cleanup_temp(self) -> int:
        return 0  # uploads are single PUTs: nothing is left half-written
