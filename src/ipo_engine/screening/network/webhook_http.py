"""
Sending a webhook safely.

A webhook URL is chosen by a customer, so the server must not be talked into reaching things on its
own network (SSRF). Every address the host name resolves to must be a public one, the connection is
then made to that very address (so a second DNS answer cannot swap it), TLS is checked against the
original host name, redirects are not followed, and the response body is not read past a few KB.
https only; plain http to a loopback address is allowed only when the operator turns on
``ALLOW_PRIVATE_WEBHOOK_TARGETS`` (development, tests).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ipo_engine.screening.network.http import HttpError

TIMEOUT_S = 10.0
Resolver = Callable[..., list[tuple[Any, ...]]]


class Sender(Protocol):
    def send(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        """POST ``body``; return the HTTP status. Raises HttpError if it could not be sent."""


@dataclass(frozen=True)
class Target:
    scheme: str
    host: str
    port: int
    path: str
    ips: tuple[str, ...]


def validate_target(
    url: str, *, allow_private: bool = False, resolver: Resolver = socket.getaddrinfo
) -> Target:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise HttpError("The webhook URL must be an https:// address.")
    if parts.username or parts.password:
        raise HttpError("The webhook URL must not contain credentials.")
    if parts.scheme == "http" and not allow_private:
        raise HttpError("The webhook URL must be an https:// address.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = resolver(parts.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HttpError("The webhook host does not resolve.") from exc
    ips = tuple(dict.fromkeys(str(info[4][0]) for info in infos))
    if not ips:
        raise HttpError("The webhook host does not resolve.")
    if not allow_private:
        for ip in ips:
            if not ipaddress.ip_address(ip).is_global:
                raise HttpError("The webhook host resolves to a non-public address.")
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return Target(parts.scheme, parts.hostname, port, path, ips)


class _Pinned(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, port: int) -> None:
        super().__init__(host, port, timeout=TIMEOUT_S, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)  # type: ignore[attr-defined]


class _PinnedPlain(http.client.HTTPConnection):
    def __init__(self, host: str, ip: str, port: int) -> None:
        super().__init__(host, port, timeout=TIMEOUT_S)
        self._ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class PinnedSender:
    def __init__(
        self, *, allow_private: bool = False, resolver: Resolver = socket.getaddrinfo
    ) -> None:
        self._allow_private, self._resolver = allow_private, resolver

    def send(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        target = validate_target(url, allow_private=self._allow_private, resolver=self._resolver)
        last: Exception | None = None
        for ip in target.ips:  # first address that answers
            conn: http.client.HTTPConnection = (
                _Pinned(target.host, ip, target.port)
                if target.scheme == "https"
                else _PinnedPlain(target.host, ip, target.port)
            )
            try:
                conn.request(
                    "POST", target.path, body=body, headers={**headers, "Host": target.host}
                )
                resp = conn.getresponse()
                resp.read(4096)
                return int(resp.status)
            except (OSError, http.client.HTTPException) as exc:
                last = exc
            finally:
                conn.close()
        raise HttpError(f"delivery failed: {type(last).__name__}")
