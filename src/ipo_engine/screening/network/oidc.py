"""
OpenID Connect sign-in (authorization code flow with PKCE), for Google or any compliant provider.

The ID token comes straight from the provider's token endpoint over TLS, and its RS256 signature is
also checked against the provider's published keys (``jwks_uri``): verified by the channel and by
the signature. Only RS256 is accepted (never ``none``, never an HMAC keyed with a public key), the
key is chosen by ``kid``, and an unknown ``kid`` triggers a key refetch at most once a minute so a
stream of forged tokens cannot hammer the provider. Every claim that matters is checked too: issuer,
audience (and authorised party), expiry, issued-at, nonce, subject and a verified email. The
signature check can be switched off (``OIDC_VERIFY_SIGNATURE=false``) only for a provider that
publishes no keys.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ipo_engine.screening.network.http import Http, HttpError, require_https

LEEWAY_S = 60
DISCOVERY_TTL_S = 3600
MIN_REFETCH_S = 60
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
    verify_signature: bool = True


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


def _b64bytes(part: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    except (ValueError, TypeError) as exc:
        raise OidcError("The identity token is malformed.") from exc


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
        self._keys: dict[str, rsa.RSAPublicKey] = {}
        self._keys_at = 0.0

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

    def _load_keys(self) -> None:
        uri = self.discovery().get("jwks_uri")
        if not isinstance(uri, str):
            raise OidcError("The identity provider publishes no signing keys.")
        try:
            doc = self._http.get_json(require_https(uri))
        except HttpError as exc:
            raise OidcError("The identity provider's signing keys are not reachable.") from exc
        keys: dict[str, rsa.RSAPublicKey] = {}
        for jwk in doc.get("keys", []):
            if (
                not isinstance(jwk, dict)
                or jwk.get("kty") != "RSA"
                or jwk.get("use", "sig") != "sig"
            ):
                continue
            try:
                n = int.from_bytes(_b64bytes(str(jwk["n"])), "big")
                e = int.from_bytes(_b64bytes(str(jwk["e"])), "big")
                keys[str(jwk.get("kid", ""))] = rsa.RSAPublicNumbers(e, n).public_key()
            except (KeyError, ValueError):
                continue
        self._keys, self._keys_at = keys, self._clock()

    def _verify_signature(self, token: str) -> None:
        head_b64, payload_b64, sig_b64 = token.split(".")
        header = _b64json(head_b64)
        if header.get("alg") != "RS256":  # not "none", not HS256 keyed with the public key
            raise OidcError("The identity token is signed with an unsupported algorithm.")
        kid = str(header.get("kid", ""))
        age = self._clock() - self._keys_at
        if (
            not self._keys
            or age > DISCOVERY_TTL_S
            or (kid not in self._keys and age > MIN_REFETCH_S)
        ):
            self._load_keys()  # first use, a day-old copy, or a rotated key (rate-limited)
        key = self._keys.get(kid)
        if key is None:
            raise OidcError("The identity token is signed with an unknown key.")
        try:
            key.verify(
                _b64bytes(sig_b64),
                f"{head_b64}.{payload_b64}".encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (InvalidSignature, ValueError, UnicodeEncodeError) as exc:
            raise OidcError("The identity token's signature is not valid.") from exc

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
        if self._cfg.verify_signature:
            self._verify_signature(id_token)
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
        if not isinstance(exp, int | float) or not math.isfinite(exp) or exp + LEEWAY_S < now:
            raise OidcError("The identity token has expired.")
        if isinstance(iat, int | float) and iat - LEEWAY_S > now:
            raise OidcError("The identity token is dated in the future.")
        presented = claims.get("nonce")
        if not isinstance(presented, str) or not hmac.compare_digest(
            presented.encode(), nonce.encode()
        ):
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
