"""An in-process OpenID Connect provider for tests: no network, real PKCE and nonce checks."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ISSUER = "https://idp.test"
CLIENT_ID = "client-123"
CLIENT_SECRET = "s3cret"


def _b64(obj: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _int_b64(n: int) -> str:
    return (
        base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()
    )


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


_DEFAULT_KEY = new_key()  # one key for the test session: generating RSA keys is slow


def jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, str]:
    pub = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _int_b64(pub.n),
        "e": _int_b64(pub.e),
    }


def make_id_token(
    claims: dict[str, Any],
    key: rsa.RSAPrivateKey | None = None,
    kid: str = "k1",
    header: dict[str, Any] | None = None,
) -> str:
    """A real RS256-signed token (``header`` overrides the JOSE header to forge odd ones)."""
    head = {"alg": "RS256", "typ": "JWT", "kid": kid, **(header or {})}
    signing_input = f"{_b64(head)}.{_b64(claims)}"
    sig = (key or _DEFAULT_KEY).sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return signing_input + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


class FakeIdp:
    """Implements the ``Http`` interface the app uses, and plays the browser's part at the IdP."""

    def __init__(self) -> None:
        self.codes: dict[str, dict[str, Any]] = {}
        self.requests: list[tuple[str, str]] = []
        self.override: dict[str, Any] = {}  # claims to force into the next token (to test refusals)
        self.keys: dict[str, rsa.RSAPrivateKey] = {
            "k1": _DEFAULT_KEY
        }  # what the provider publishes
        self.signer: tuple[rsa.RSAPrivateKey, str] | None = None  # sign the next token otherwise
        self.header: dict[str, Any] = {}  # JOSE header overrides for the next token
        self.publish_jwks = True

    # --- the Http interface -------------------------------------------------------------
    def get_json(self, url: str) -> dict[str, Any]:
        self.requests.append(("GET", url))
        if url == f"{ISSUER}/jwks":
            return {"keys": [jwk(k, kid) for kid, k in self.keys.items()]}
        assert url == f"{ISSUER}/.well-known/openid-configuration", url
        doc = {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token",
        }
        if self.publish_jwks:
            doc["jwks_uri"] = f"{ISSUER}/jwks"
        return doc

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
        key, kid = self.signer or (_DEFAULT_KEY, "k1")
        return {
            "id_token": make_id_token(claims, key, kid, self.header),
            "access_token": "unused",
        }

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
