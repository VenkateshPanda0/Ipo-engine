"""The ID token's signature is checked against the provider's published keys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from tests.screening.integration.api.fake_idp import (
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    FakeIdp,
    jwk,
    make_id_token,
    new_key,
)

from ipo_engine.screening.network.oidc import OidcClient, OidcConfig, OidcError


def _claims(**over: Any) -> dict[str, Any]:
    now = int(time.time())
    return {
        "iss": ISSUER, "aud": CLIENT_ID, "sub": "s-1", "email": "a@x.example",
        "email_verified": True, "iat": now, "exp": now + 300, "nonce": "n-1", **over,
    }  # fmt: skip


def _client(idp: FakeIdp, clock: Any = time.time, **cfg: Any) -> OidcClient:
    config = OidcConfig(
        issuer=ISSUER, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        redirect_uri="http://x/cb", **cfg,
    )  # fmt: skip
    return OidcClient(config, idp, clock=clock)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_a_correctly_signed_token_is_accepted() -> None:
    who = _client(FakeIdp()).validate(make_id_token(_claims()), nonce="n-1")
    assert who.email == "a@x.example" and who.subject == "s-1"


def test_a_token_whose_payload_was_changed_after_signing_is_refused() -> None:
    head, payload, sig = make_id_token(_claims()).split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged["email"] = "ceo@victim.example"
    bad = ".".join([head, _b64(json.dumps(forged).encode()), sig])
    with pytest.raises(OidcError, match="signature is not valid"):
        _client(FakeIdp()).validate(bad, nonce="n-1")


def test_a_token_signed_by_someone_elses_key_is_refused() -> None:
    with pytest.raises(OidcError, match="signature is not valid"):
        _client(FakeIdp()).validate(make_id_token(_claims(), key=new_key()), nonce="n-1")


@pytest.mark.parametrize("alg", ["none", "HS256", "ES256", "RS512"])
def test_only_rs256_is_accepted(alg: str) -> None:
    token = make_id_token(_claims(), header={"alg": alg})
    with pytest.raises(OidcError, match="unsupported algorithm"):
        _client(FakeIdp()).validate(token, nonce="n-1")


def test_an_hmac_token_keyed_with_the_public_key_is_refused() -> None:
    """The classic key-confusion attack: HS256 with the published RSA key as the secret."""
    idp = FakeIdp()
    public = json.dumps(jwk(idp.keys["k1"], "k1")).encode()
    head = _b64(json.dumps({"alg": "HS256", "kid": "k1"}).encode())
    body = _b64(json.dumps(_claims()).encode())
    sig = _b64(hmac.new(public, f"{head}.{body}".encode(), hashlib.sha256).digest())
    with pytest.raises(OidcError, match="unsupported algorithm"):
        _client(idp).validate(f"{head}.{body}.{sig}", nonce="n-1")


def test_a_stripped_signature_is_refused() -> None:
    head, payload, _ = make_id_token(_claims()).split(".")
    with pytest.raises(OidcError):
        _client(FakeIdp()).validate(f"{head}.{payload}.", nonce="n-1")


def test_a_rotated_key_is_picked_up_with_one_refetch() -> None:
    idp = FakeIdp()
    t = [1000.0]
    client = _client(idp, clock=lambda: t[0])
    client.validate(make_id_token(_claims(exp=2000, iat=1000), key=idp.keys["k1"]), nonce="n-1")
    fresh = new_key()
    idp.keys["k2"] = fresh  # the provider adds a key
    t[0] += 120  # past the refetch floor
    who = client.validate(
        make_id_token(_claims(exp=2000, iat=1000), key=fresh, kid="k2"), nonce="n-1"
    )
    assert who.subject == "s-1"
    assert sum(1 for m, u in idp.requests if u.endswith("/jwks")) == 2  # first load + one refetch


def test_forged_unknown_key_ids_cannot_make_the_server_hammer_the_provider() -> None:
    idp = FakeIdp()
    t = [1000.0]
    client = _client(idp, clock=lambda: t[0])
    client.validate(make_id_token(_claims(exp=2000, iat=1000)), nonce="n-1")
    before = sum(1 for m, u in idp.requests if u.endswith("/jwks"))
    for n in range(20):
        with pytest.raises(OidcError, match="unknown key"):
            client.validate(
                make_id_token(_claims(exp=2000, iat=1000), kid=f"evil-{n}"), nonce="n-1"
            )
        t[0] += 1  # a second apart: well inside the one-a-minute floor
    assert sum(1 for m, u in idp.requests if u.endswith("/jwks")) - before <= 1


def test_a_provider_with_no_published_keys_is_refused_unless_checking_is_switched_off() -> None:
    idp = FakeIdp()
    idp.publish_jwks = False
    with pytest.raises(OidcError, match="no signing keys"):
        _client(idp).validate(make_id_token(_claims()), nonce="n-1")
    who = _client(idp, verify_signature=False).validate(make_id_token(_claims()), nonce="n-1")
    assert who.email == "a@x.example"


def test_the_other_claim_checks_still_apply_to_a_validly_signed_token() -> None:
    with pytest.raises(OidcError, match="does not match"):
        _client(FakeIdp()).validate(make_id_token(_claims(nonce="other")), nonce="n-1")
    with pytest.raises(OidcError, match="expired"):
        _client(FakeIdp()).validate(make_id_token(_claims(exp=1)), nonce="n-1")


def test_sign_in_through_the_app_refuses_a_forged_token(tmp_path: Any) -> None:
    from tests.screening.integration.api.test_signin import Site, _error, _seed

    s = Site(tmp_path)
    try:
        _seed(s)
        s.idp.signer = (new_key(), "k1")  # an attacker's key, claiming the published key id
        browser, done = s.sign_in("ann@alpha.example")
        assert "signature is not valid" in _error(done)
        assert browser.get("/api/v1/me").status_code == 401
    finally:
        s.close()
