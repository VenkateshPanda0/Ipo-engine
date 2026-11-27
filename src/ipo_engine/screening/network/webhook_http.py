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

import contextlib
import http.client
import ipaddress
import socket
import ssl
import threading
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ipo_engine.screening.network.http import HttpError

TIMEOUT_S = 10.0
TOTAL_S = 20.0
"""The most a whole delivery (connect, send, read) may take."""
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


_TRANSITIONAL = tuple(
    ipaddress.ip_network(n)
    for n in (
        "64:ff9b::/96",  # NAT64: reaches an IPv4 address (even a private one) through a gateway
        "64:ff9b:1::/48",
        "::/96",  # IPv4-compatible: ::127.0.0.1
        "2002::/16",  # 6to4: embeds an IPv4 address
    )
)


def _is_transitional(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """An IPv6 address that smuggles an IPv4 one past an ``is_global`` check."""
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return True
        return any(addr in net for net in _TRANSITIONAL)
    return False


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
    try:
        explicit_port = parts.port
    except ValueError as exc:  # ":99999" or ":abc"
        raise HttpError("The webhook URL has an invalid port.") from exc
    if explicit_port == 0:
        raise HttpError("The webhook URL has an invalid port.")
    port = explicit_port or (443 if parts.scheme == "https" else 80)
    try:
        infos = resolver(parts.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HttpError("The webhook host does not resolve.") from exc
    ips = tuple(dict.fromkeys(str(info[4][0]) for info in infos))
    if not ips:
        raise HttpError("The webhook host does not resolve.")
    if not allow_private:
        for ip in ips:
            addr = ipaddress.ip_address(ip)
            if not addr.is_global or _is_transitional(addr):
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


def _cut_off(conn: http.client.HTTPConnection) -> None:
    """Abort a delivery that has run too long: shutting the socket wakes the blocked read."""
    sock = conn.sock
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)


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
                # TIMEOUT_S limits each socket operation, so a server that drips one byte at a time
                # could hold this thread for ever: a timer cuts the whole exchange off.
                guard = threading.Timer(TOTAL_S, _cut_off, args=(conn,))
                guard.daemon = True
                guard.start()
                try:
                    conn.request(
                        "POST", target.path, body=body, headers={**headers, "Host": target.host}
                    )
                    resp = conn.getresponse()
                    resp.read(4096)
                    return int(resp.status)
                finally:
                    guard.cancel()
            except (OSError, http.client.HTTPException) as exc:
                last = exc
            finally:
                conn.close()
        raise HttpError(f"delivery failed: {type(last).__name__}")
