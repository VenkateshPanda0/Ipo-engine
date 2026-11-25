"""
Authentication and authorization.

Identity and role come only from server-side configuration. A client-supplied
role header (``X-User-Role``) is ignored — in ruleset 1.0.0 it let any key holder
act as a reviewer (baseline defect D11).

When no keys are configured the API runs in local single-user mode: requests are
attributed to the ``local-user`` principal with the admin role. Use this only on a
trusted machine.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request, status

from ipo_engine.screening.core.config import Settings, get_settings


class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"


_RANK = {Role.VIEWER: 0, Role.ANALYST: 1, Role.REVIEWER: 2, Role.ADMIN: 3}


@dataclass(frozen=True)
class Principal:
    """Authenticated caller."""

    user_id: str
    role: Role
    authenticated: bool

    def has(self, role: Role) -> bool:
        return _RANK[self.role] >= _RANK[role]


logger = logging.getLogger("ipo_engine.screening.security")


class InsecureConfiguration(RuntimeError):
    """The configuration would expose the API in a way the operator has not chosen."""


def check_production_auth(settings: Settings) -> None:
    """Refuse a production start with no API keys, unless ALLOW_UNAUTHENTICATED is set.

    With no keys every request is the ``local-user`` admin. That is fine on a laptop and wrong on a
    network, and a container image defaults to production, so the unsafe state must be chosen, not
    reached by forgetting a variable.
    """
    if not settings.is_production or settings.auth_enabled:
        return
    if not settings.allow_unauthenticated:
        raise InsecureConfiguration(
            "APP_ENV=production but no API keys are configured, so every caller would be an "
            "admin. Set API_KEYS (entries '<user>|<role>|sha256=<digest>'; make a digest with "
            "`ipo keys hash`), or set ALLOW_UNAUTHENTICATED=true to run without authentication "
            "on purpose (for example behind a gateway that authenticates for you)."
        )
    logger.warning(
        "RUNNING WITHOUT AUTHENTICATION: APP_ENV=production with no API keys and "
        "ALLOW_UNAUTHENTICATED=true. Every caller is an admin. Responses carry "
        "'X-IPO-Engine-Auth: disabled'."
    )


LOCAL_PRINCIPAL = Principal(user_id="local-user", role=Role.ADMIN, authenticated=False)


@dataclass(frozen=True)
class _KeyEntry:
    user_id: str
    role: Role
    digest: bytes


def _digest(key: str) -> bytes:
    return hashlib.sha256(key.encode("utf-8")).digest()


def parse_api_keys(settings: Settings) -> tuple[_KeyEntry, ...]:
    """Parse API_KEYS / API_KEY into key entries (keys are held only as digests).

    Raises ``ValueError`` for malformed configuration; ``create_app`` calls this at
    startup so a bad value fails fast instead of on the first request.
    """
    return _parse(settings.api_keys or "", settings.api_key or "")


@lru_cache(maxsize=8)
def _parse(api_keys: str, api_key: str) -> tuple[_KeyEntry, ...]:
    entries: list[_KeyEntry] = []
    for raw in api_keys.split(","):
        raw = raw.strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != 3 or not all(parts):
            raise ValueError("API_KEYS entries must be '<user_id>|<role>|<key or sha256=hex>'.")
        user_id, role, secret = parts
        try:
            role_value = Role(role)
        except ValueError:
            raise ValueError(
                f"API_KEYS: unknown role {role!r} (use viewer, analyst, reviewer or admin)."
            ) from None
        if secret.startswith("sha256="):
            try:
                digest = bytes.fromhex(secret.removeprefix("sha256="))
            except ValueError:
                raise ValueError("API_KEYS: sha256= digest must be hexadecimal.") from None
            if len(digest) != hashlib.sha256().digest_size:
                raise ValueError("API_KEYS: sha256= digest must be 64 hex characters.")
        else:
            digest = _digest(secret)
        entries.append(_KeyEntry(user_id=user_id, role=role_value, digest=digest))
    if api_key:
        entries.append(_KeyEntry(user_id="api-user", role=Role.ANALYST, digest=_digest(api_key)))
    return tuple(entries)


def authenticate(settings: Settings, authorization: str | None) -> Principal:
    """Resolve the principal for a request; raises 401 on bad credentials."""
    entries = parse_api_keys(settings)
    if not entries:
        return LOCAL_PRINCIPAL
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")
    presented = _digest(token.strip())
    match: _KeyEntry | None = None
    for entry in entries:  # compare against every entry: no early exit timing signal
        if hmac.compare_digest(presented, entry.digest):
            match = entry
    if match is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")
    return Principal(user_id=match.user_id, role=match.role, authenticated=True)


def request_settings(request: Request) -> Settings:
    """Settings of the application instance serving this request."""
    container = getattr(request.app.state, "container", None)
    return container.settings if container is not None else get_settings()


def get_principal(
    request: Request,
    settings: Settings = Depends(request_settings),
    authorization: str | None = Header(default=None),
) -> Principal:
    """FastAPI dependency returning the authenticated principal."""
    principal = authenticate(settings, authorization)
    request.state.principal = principal.user_id  # for the request log line
    return principal


def require_api_key(principal: Principal = Depends(get_principal)) -> Principal:
    """Backward-compatible dependency: any authenticated (or local) principal."""
    return principal


def require_role(role: Role):  # type: ignore[no-untyped-def]
    """Dependency factory enforcing a minimum role."""

    def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"{role.value} role required.")
        return principal

    return _check


require_reviewer_role = require_role(Role.REVIEWER)
