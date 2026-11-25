"""
OpenID Connect sign-in (authorization code flow with PKCE), for Google or any compliant provider.

The ID token is taken directly from the provider's token endpoint over TLS, in answer to a request
that carries our client secret and the PKCE verifier. OpenID Connect Core 3.1.3.7 (step 6) lets a
client rely on that channel instead of checking the token's signature, so no JWT library is needed,
and a token that arrives any other way is never accepted. Every claim that matters is checked:
issuer, audience (and authorised party), expiry, issued-at, nonce, subject and a verified email.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from ipo_engine.screening.network.http import Http, HttpError, require_https

LEEWAY_S = 60
DISCOVERY_TTL_S = 3600
_GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class OidcError(RuntimeError):
    """The sign-in could not be completed; the message is safe to show the person."""


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...] = ("openid", "email", "profile")


@dataclass(frozen=True)
class OidcIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str | None
    hosted_domain: str | None


def new_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge) for the S256 method."""
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def _b64json(part: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise OidcError("The identity token is malformed.") from exc
    if not isinstance(value, dict):
        raise OidcError("The identity token is malformed.")
    return value


class OidcClient:
    def __init__(self, config: OidcConfig, http: Http, *, clock: Any = time.time) -> None:
        self._cfg = config
        self._http = http
        self._clock = clock
        self._doc: dict[str, Any] | None = None
        self._doc_at = 0.0

    def discovery(self) -> dict[str, Any]:
        if self._doc is not None and self._clock() - self._doc_at < DISCOVERY_TTL_S:
            return self._doc
        url = self._cfg.issuer.rstrip("/") + "/.well-known/openid-configuration"
        try:
            doc = self._http.get_json(require_https(url))
        except HttpError as exc:
            raise OidcError("The identity provider is not reachable.") from exc
        if str(doc.get("issuer", "")).rstrip("/") != self._cfg.issuer.rstrip("/"):
            raise OidcError("The identity provider's issuer does not match the configuration.")
        for key in ("authorization_endpoint", "token_endpoint"):
            try:
                require_https(str(doc.get(key, "")))
            except HttpError as exc:
                raise OidcError(f"The identity provider's {key} is not usable.") from exc
        self._doc, self._doc_at = doc, self._clock()
        return doc

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self._cfg.client_id,
                "redirect_uri": self._cfg.redirect_uri,
                "scope": " ".join(self._cfg.scopes),
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{self.discovery()['authorization_endpoint']}?{query}"

    def exchange(self, *, code: str, code_verifier: str, nonce: str) -> OidcIdentity:
        try:
            answer = self._http.post_form(
                self.discovery()["token_endpoint"],
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._cfg.redirect_uri,
                    "client_id": self._cfg.client_id,
                    "client_secret": self._cfg.client_secret,
                    "code_verifier": code_verifier,
                },
            )
        except HttpError as exc:
            raise OidcError("The identity provider rejected the sign-in.") from exc
        token = answer.get("id_token")
        if not isinstance(token, str):
            raise OidcError("The identity provider returned no identity token.")
        return self.validate(token, nonce=nonce)

    def validate(self, id_token: str, *, nonce: str) -> OidcIdentity:
        parts = id_token.split(".")
        if len(parts) != 3:
            raise OidcError("The identity token is malformed.")
        claims = _b64json(parts[1])
        now = self._clock()
        issuer = str(claims.get("iss", ""))
        accepted = _GOOGLE_ISSUERS if self._cfg.issuer in _GOOGLE_ISSUERS else (self._cfg.issuer,)
        if issuer not in accepted:
            raise OidcError("The identity token was issued by someone else.")
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if self._cfg.client_id not in audiences:
            raise OidcError("The identity token is for a different application.")
        if len(audiences) > 1 and claims.get("azp") != self._cfg.client_id:
            raise OidcError("The identity token is for a different application.")
        exp, iat = claims.get("exp"), claims.get("iat")
        if not isinstance(exp, int | float) or exp + LEEWAY_S < now:
            raise OidcError("The identity token has expired.")
        if isinstance(iat, int | float) and iat - LEEWAY_S > now:
            raise OidcError("The identity token is dated in the future.")
        presented = claims.get("nonce")
        if not isinstance(presented, str) or not hmac.compare_digest(presented, nonce):
            raise OidcError("The sign-in does not match the request that started it.")
        subject, email = claims.get("sub"), claims.get("email")
        if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
            raise OidcError("The identity token has no subject or email.")
        verified = claims.get("email_verified")
        verified = verified is True or (isinstance(verified, str) and verified.lower() == "true")
        name = claims.get("name")
        hd = claims.get("hd")
        return OidcIdentity(
            subject=subject,
            email=email,
            email_verified=verified,
            name=name if isinstance(name, str) else None,
            hosted_domain=hd if isinstance(hd, str) else None,
        )
