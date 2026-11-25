"""A small outbound HTTP client with hard limits, and the interface tests replace.

The interface (``Http``) is what the rest of the code depends on, so tests run against an in-process
fake and the whole sign-in flow is exercised with no network at all.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

MAX_BYTES = 1_000_000
TIMEOUT_S = 10.0


class HttpError(RuntimeError):
    """The remote service could not be reached or answered badly."""


class Http(Protocol):
    def get_json(self, url: str) -> dict[str, Any]: ...

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]: ...


def require_https(url: str) -> str:
    """Only https, except a loopback address (a local identity provider while developing)."""
    parts = urllib.parse.urlsplit(url)
    loopback = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise HttpError(f"refusing a non-https URL: {parts.scheme}://{parts.hostname}")
    if not parts.hostname:
        raise HttpError("URL has no host")
    return url


class UrllibHttp:
    """The real client: https only, a timeout, no redirects to other schemes, a size cap."""

    def _open(self, req: urllib.request.Request) -> dict[str, Any]:
        require_https(req.full_url)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                raw = resp.read(MAX_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HttpError(f"request failed: {type(exc).__name__}") from exc
        if len(raw) > MAX_BYTES:
            raise HttpError("response too large")
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise HttpError("response was not JSON") from exc
        if not isinstance(value, dict):
            raise HttpError("response was not a JSON object")
        return value

    def get_json(self, url: str) -> dict[str, Any]:
        return self._open(urllib.request.Request(url, headers={"Accept": "application/json"}))

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        return self._open(req)
