"""An in-process OpenID Connect provider for tests: no network, real PKCE and nonce checks."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from typing import Any

ISSUER = "https://idp.test"
CLIENT_ID = "client-123"
CLIENT_SECRET = "s3cret"


def _b64(obj: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def make_id_token(claims: dict[str, Any]) -> str:
    return f"{_b64({'alg': 'RS256'})}.{_b64(claims)}.c2ln"  # signature is not checked (see oidc.py)


class FakeIdp:
    """Implements the ``Http`` interface the app uses, and plays the browser's part at the IdP."""

    def __init__(self) -> None:
        self.codes: dict[str, dict[str, Any]] = {}
        self.requests: list[tuple[str, str]] = []
        self.override: dict[str, Any] = {}  # claims to force into the next token (to test refusals)

    # --- the Http interface -------------------------------------------------------------
    def get_json(self, url: str) -> dict[str, Any]:
        self.requests.append(("GET", url))
        assert url == f"{ISSUER}/.well-known/openid-configuration", url
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
        }

    def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        self.requests.append(("POST", url))
        assert url == f"{ISSUER}/token"
        assert data["client_id"] == CLIENT_ID and data["client_secret"] == CLIENT_SECRET
        entry = self.codes.pop(data["code"], None)  # a code works once
        assert entry is not None, "unknown or reused authorization code"
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert challenge == entry["challenge"], "PKCE verifier does not match the challenge"
        assert data["redirect_uri"] == entry["redirect_uri"]
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": entry["sub"],
            "email": entry["email"],
            "email_verified": True,
            "name": entry.get("name", "Test Person"),
            "iat": now,
            "exp": now + 300,
            "nonce": entry["nonce"],
            **self.override,
        }
        return {"id_token": make_id_token(claims), "access_token": "unused"}

    # --- the person at the provider's sign-in page --------------------------------------
    def approve(self, authorize_url: str, *, email: str, sub: str | None = None) -> str:
        """The user signs in at the IdP; returns the callback URL the browser is sent to."""
        parts = urllib.parse.urlsplit(authorize_url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        assert q["response_type"] == "code" and q["code_challenge_method"] == "S256"
        assert q["client_id"] == CLIENT_ID and q["state"] and q["nonce"]
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "challenge": q["code_challenge"],
            "nonce": q["nonce"],
            "redirect_uri": q["redirect_uri"],
            "email": email,
            "sub": sub or f"sub-{hashlib.sha256(email.encode()).hexdigest()[:12]}",
        }
        back = urllib.parse.urlencode({"code": code, "state": q["state"]})
        return f"{q['redirect_uri']}?{back}"
