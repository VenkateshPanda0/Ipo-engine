"""Sign-in with an OpenID Connect provider (a fake one), browser sessions and CSRF."""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.screening.integration.api.accounts_world import make_member
from tests.screening.integration.api.fake_idp import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeIdp

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.core.security import Role
from ipo_engine.screening.db.models import OAuthStateRow, SessionRow
from ipo_engine.screening.main import create_app

BASE = "http://localhost:3000"


class Site:
    """A browser talking to the app, with a fake identity provider behind Google sign-in."""

    def __init__(self, tmp_path: Any, **env: Any) -> None:
        self.idp = FakeIdp()
        https = env.get("TRUST_HTTPS") or env.get("APP_ENV") == "production"
        self.scheme = "https" if https else "http"
        values = {
            "DATA_DIR": str(tmp_path / "data"),
            "DATABASE_URL": f"sqlite:///{tmp_path / 'site.db'}",
            "ACCOUNTS_ENABLED": "true",
            "GOOGLE_CLIENT_ID": CLIENT_ID,
            "GOOGLE_CLIENT_SECRET": CLIENT_SECRET,
            "OIDC_ISSUER": ISSUER,
            "PUBLIC_BASE_URL": BASE,
            **{k: str(v) for k, v in env.items()},
        }
        self.app = create_app(Settings(**values), inline_processing=True, http=self.idp)  # type: ignore[arg-type]
        self.c = TestClient(self.app, follow_redirects=False, base_url="http://api.test")
        self.c.__enter__()

    @property
    def container(self) -> Any:
        return self.app.state.container

    def browser(self) -> TestClient:
        return TestClient(self.app, follow_redirects=False, base_url=f"{self.scheme}://api.test")

    def sign_in(
        self,
        email: str,
        *,
        client: TestClient | None = None,
        invitation: str | None = None,
        next_url: str | None = None,
        sub: str | None = None,
    ) -> tuple[TestClient, Any]:
        """Run the redirect dance in one browser; returns (browser, final callback response)."""
        b = client or self.browser()
        params = {k: v for k, v in (("invitation", invitation), ("next", next_url)) if v}
        start = b.get("/api/v1/auth/login/google", params=params)
        assert start.status_code == 303, start.text
        callback = self.idp.approve(start.headers["location"], email=email, sub=sub)
        parts = urllib.parse.urlsplit(callback)
        return b, b.get(parts.path + "?" + parts.query)

    def close(self) -> None:
        self.c.__exit__(None, None, None)


@pytest.fixture
def site(tmp_path: Any) -> Any:
    made: list[Site] = []

    def build(**env: Any) -> Site:
        s = Site(tmp_path if not made else tmp_path / f"s{len(made)}", **env)
        made.append(s)
        return s

    yield build
    for s in made:
        s.close()


def _seed(site: Site, email: str = "ann@alpha.example", role: Role = Role.ADMIN) -> tuple[str, str]:
    acc = site.container.accounts
    org = acc.create_org("Alpha Capital")["id"]
    user = acc.get_or_create_user(email)
    acc.add_member(org, user["id"], role, actor="test", owner=True)
    return org, user["id"]


def _error(resp: Any) -> str:
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(resp.headers["location"]).query)
    return str(q.get("error", [""])[0])


def test_providers_say_what_is_available(site: Callable[..., Site]) -> None:
    s = site()
    body = s.c.get("/api/v1/auth/providers").json()
    assert body == {"accounts": True, "google": True, "signup": "invite"}


def test_google_is_off_without_a_client_id(tmp_path: Any, app_factory: Any) -> None:
    client = app_factory(ACCOUNTS_ENABLED="true")
    assert client.get("/api/v1/auth/providers").json()["google"] is False
    r = client.get("/api/v1/auth/login/google", follow_redirects=False)
    assert r.status_code == 303 and "error=" in r.headers["location"]


def test_full_sign_in_sets_an_httponly_session_cookie_and_reaches_the_api(
    site: Callable[..., Site],
) -> None:
    s = site()
    org, user = _seed(s)
    browser, done = s.sign_in("Ann@Alpha.example")
    assert done.status_code == 303 and done.headers["location"] == f"{BASE}/"
    cookie = next(h for h in done.headers.get_list("set-cookie") if h.startswith("ipo_session="))
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    me = browser.get("/api/v1/me").json()
    assert me["user_id"] == user and me["org_id"] == org and me["role"] == "admin"
    assert browser.get("/api/v1/cases").status_code == 200


def test_the_authorization_request_uses_pkce_state_and_nonce(site: Callable[..., Site]) -> None:
    s = site()
    start = s.browser().get("/api/v1/auth/login/google")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(start.headers["location"]).query))
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) >= 43
    assert q["redirect_uri"] == f"{BASE}/api/v1/auth/callback/google"
    assert len(q["state"]) >= 32 and len(q["nonce"]) >= 24 and q["scope"] == "openid email profile"
    with s.container.db.session() as db:
        stored = db.execute(select(OAuthStateRow.state_hash)).scalars().all()
    assert q["state"] not in stored and all(len(h) == 64 for h in stored)  # hashed at rest


def test_invite_only_refuses_a_stranger_and_creates_nothing(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    browser, done = s.sign_in("stranger@elsewhere.example")
    assert "login" in done.headers["location"] and "No invitation" in _error(done)
    assert "ipo_session" not in "".join(done.headers.get_list("set-cookie"))
    assert browser.get("/api/v1/me").status_code == 401
    with s.container.db.session() as db:
        from ipo_engine.screening.db.models import UserRow

        emails = set(db.execute(select(UserRow.email)).scalars())
    assert "stranger@elsewhere.example" not in emails


def test_an_invitation_adds_the_person_with_its_role_once(site: Callable[..., Site]) -> None:
    s = site()
    org, admin_id = _seed(s)
    inv = s.container.accounts.invite(org, "new@beta.example", Role.REVIEWER, actor=admin_id)
    preview = s.c.get("/api/v1/auth/invitation", params={"token": inv["token"]}).json()
    assert preview == {
        "organisation": "Alpha Capital",
        "email": "new@beta.example",
        "role": "reviewer",
    }
    browser, done = s.sign_in("new@beta.example", invitation=inv["token"])
    assert done.status_code == 303 and "error" not in done.headers["location"]
    me = browser.get("/api/v1/me").json()
    assert me["role"] == "reviewer" and me["org_id"] == org
    # the link is spent
    assert s.c.get("/api/v1/auth/invitation", params={"token": inv["token"]}).status_code == 404
    again = s.browser().get("/api/v1/auth/login/google", params={"invitation": inv["token"]})
    assert (
        "no+longer+valid" in again.headers["location"] or "no%20longer" in again.headers["location"]
    )


def test_an_invitation_cannot_be_used_by_another_address(site: Callable[..., Site]) -> None:
    s = site()
    org, admin_id = _seed(s)
    inv = s.container.accounts.invite(org, "right@x.example", Role.ANALYST, actor=admin_id)
    _, done = s.sign_in("wrong@x.example", invitation=inv["token"])
    assert "different email" in _error(done)


def test_revoked_and_expired_invitations_do_not_work(site: Callable[..., Site]) -> None:
    s = site()
    org, admin_id = _seed(s)
    acc = s.container.accounts
    revoked = acc.invite(org, "a@x.example", Role.VIEWER, actor=admin_id)
    acc.revoke_invitation(org, revoked["id"], actor=admin_id)
    assert acc.invitation_preview(revoked["token"]) is None
    expired = acc.invite(org, "b@x.example", Role.VIEWER, actor=admin_id, days=1)
    from ipo_engine.screening.db.models import InvitationRow

    with s.container.db.session() as db:
        db.get(InvitationRow, expired["id"]).expires_at = datetime.now(tz=UTC) - timedelta(hours=1)
    assert acc.invitation_preview(expired["token"]) is None


def test_open_signup_gives_a_new_person_an_organisation_of_their_own(
    site: Callable[..., Site],
) -> None:
    s = site(SIGNUP_MODE="open")
    browser, done = s.sign_in("founder@new.example")
    assert "error" not in done.headers["location"]
    me = browser.get("/api/v1/me").json()
    assert me["role"] == "admin"
    assert (
        browser.post("/api/v1/cases", json={"company_name": "X Ltd"}).status_code == 403
    )  # no CSRF
    csrf = browser.get("/api/v1/auth/csrf").json()["csrf_token"]
    made = browser.post(
        "/api/v1/cases", json={"company_name": "X Ltd"}, headers={"X-CSRF-Token": csrf}
    )
    assert made.status_code == 201


def test_a_known_user_is_linked_by_verified_email_and_then_by_subject(
    site: Callable[..., Site],
) -> None:
    s = site()
    _org, user = _seed(s, "carol@alpha.example")
    _, first = s.sign_in("carol@alpha.example", sub="google-carol")
    assert "error" not in first.headers["location"]
    # same Google account, address changed at Google: still the same user (the subject is stable)
    browser, _second = s.sign_in("carol.new@alpha.example", sub="google-carol")
    assert browser.get("/api/v1/me").json()["user_id"] == user


def test_a_suspended_user_cannot_sign_in_and_their_session_dies(site: Callable[..., Site]) -> None:
    s = site()
    _, user = _seed(s)
    browser, _ = s.sign_in("ann@alpha.example")
    assert browser.get("/api/v1/me").status_code == 200
    s.container.accounts.set_user_status(user, "suspended", actor="t")
    assert browser.get("/api/v1/me").status_code == 401
    _, done = s.sign_in("ann@alpha.example")
    assert "suspended" in _error(done)


def test_email_domain_allow_list(site: Callable[..., Site]) -> None:
    s = site(ALLOWED_EMAIL_DOMAINS="alpha.example")
    _seed(s)
    s.container.accounts.get_or_create_user("x@other.example")  # known, but the domain is barred
    _, done = s.sign_in("x@other.example")
    assert "domain" in _error(done)


# ----------------------------------------------------------------- callback safety
def test_a_callback_from_another_browser_is_refused(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    victim = s.browser()  # never started a sign-in
    attacker = s.browser()
    start = attacker.get("/api/v1/auth/login/google")
    callback = s.idp.approve(start.headers["location"], email="ann@alpha.example")
    parts = urllib.parse.urlsplit(callback)
    done = victim.get(parts.path + "?" + parts.query)  # the victim is lured to the attacker's link
    assert "not started in this browser" in _error(done)
    assert victim.get("/api/v1/me").status_code == 401


def test_a_callback_cannot_be_replayed(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    browser = s.browser()
    start = browser.get("/api/v1/auth/login/google")
    callback = s.idp.approve(start.headers["location"], email="ann@alpha.example")
    parts = urllib.parse.urlsplit(callback)
    url = parts.path + "?" + parts.query
    assert "error" not in browser.get(url).headers["location"]
    again = browser.get(url)
    assert "error" in again.headers["location"]


def test_an_expired_state_is_refused(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    browser = s.browser()
    start = browser.get("/api/v1/auth/login/google")
    with s.container.db.session() as db:
        for row in db.execute(select(OAuthStateRow)).scalars():
            row.expires_at = datetime.now(tz=UTC) - timedelta(minutes=1)
    callback = s.idp.approve(start.headers["location"], email="ann@alpha.example")
    parts = urllib.parse.urlsplit(callback)
    assert "expired" in _error(browser.get(parts.path + "?" + parts.query))


@pytest.mark.parametrize(
    "nxt", ["https://evil.example/x", "//evil.example", "/\\evil.example", "javascript:alert(1)"]
)
def test_the_return_address_cannot_leave_the_site(site: Callable[..., Site], nxt: str) -> None:
    s = site()
    _seed(s)
    _, done = s.sign_in("ann@alpha.example", next_url=nxt)
    assert done.headers["location"] == f"{BASE}/"


def test_a_local_return_path_is_kept(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    _, done = s.sign_in("ann@alpha.example", next_url="/cases?x=1")
    assert done.headers["location"] == f"{BASE}/cases?x=1"


@pytest.mark.parametrize(
    "override, expect",
    [
        ({"nonce": "wrong"}, "does not match"),
        ({"aud": "someone-else"}, "different application"),
        ({"iss": "https://evil.example"}, "someone else"),
        ({"exp": 1}, "expired"),
        ({"email_verified": False}, "not verified"),
        ({"aud": [CLIENT_ID, "other"]}, "different application"),  # more than one audience, no azp
    ],
)
def test_a_bad_identity_token_is_refused(
    site: Callable[..., Site], override: dict[str, Any], expect: str
) -> None:
    s = site()
    _seed(s)
    s.idp.override = override
    browser, done = s.sign_in("ann@alpha.example")
    assert expect in _error(done), _error(done)
    assert browser.get("/api/v1/me").status_code == 401


# ---------------------------------------------------------------------------- CSRF
def test_cookie_changes_need_the_csrf_token_and_a_known_origin(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    browser, _ = s.sign_in("ann@alpha.example")
    body = {"company_name": "Acme Ltd"}
    assert browser.get("/api/v1/cases").status_code == 200  # reads need nothing
    assert browser.post("/api/v1/cases", json=body).status_code == 403
    assert (
        browser.post("/api/v1/cases", json=body, headers={"X-CSRF-Token": "guess"}).status_code
        == 403
    )
    csrf = browser.get("/api/v1/auth/csrf").json()["csrf_token"]
    ok = {"X-CSRF-Token": csrf}
    evil = {**ok, "Origin": "https://evil.example"}
    assert browser.post("/api/v1/cases", json=body, headers=evil).status_code == 403
    assert (
        browser.post("/api/v1/cases", json=body, headers={**ok, "Origin": BASE}).status_code == 201
    )
    assert browser.post("/api/v1/cases", json=body, headers=ok).status_code == 201


def test_a_bearer_token_needs_no_csrf_and_wins_over_a_cookie(site: Callable[..., Site]) -> None:
    s = site()
    org, user = _seed(s)
    tok = s.container.accounts.create_token(org_id=org, user_id=user, name="t")["token"]
    r = s.browser().post(
        "/api/v1/cases",
        json={"company_name": "Api Ltd"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201
    browser, _ = s.sign_in("ann@alpha.example")
    bad = browser.get("/api/v1/me", headers={"Authorization": "Bearer ipo_wrong"})
    assert bad.status_code == 401  # an explicit credential that fails is not rescued by a cookie


def test_the_session_cookie_is_secure_in_production_and_behind_https(
    site: Callable[..., Site],
) -> None:
    for env in ({"TRUST_HTTPS": "true"}, {"APP_ENV": "production"}):
        s = site(**env)
        _seed(s)
        _, done = s.sign_in("ann@alpha.example")
        cookie = next(
            h for h in done.headers.get_list("set-cookie") if h.startswith("ipo_session=")
        )
        assert "secure" in cookie.lower(), env


# -------------------------------------------------------------------------- sessions
def test_logout_ends_the_session_server_side(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    browser, _ = s.sign_in("ann@alpha.example")
    stolen = browser.cookies.get("ipo_session")
    csrf = browser.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert browser.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    thief = s.browser()
    thief.cookies.set("ipo_session", stolen)
    assert thief.get("/api/v1/me").status_code == 401  # the copied cookie is dead too


def test_sessions_can_be_listed_and_revoked_individually_and_in_bulk(
    site: Callable[..., Site],
) -> None:
    s = site()
    _seed(s)
    b1, _ = s.sign_in("ann@alpha.example")
    b2, _ = s.sign_in("ann@alpha.example")
    b3, _ = s.sign_in("ann@alpha.example")
    listing = b1.get("/api/v1/auth/sessions").json()
    assert len(listing) == 3 and sum(1 for x in listing if x["current"]) == 1
    assert all(len(x["id"]) == 16 for x in listing)  # a short reference, never the secret
    other = next(x for x in listing if not x["current"])
    csrf1 = b1.get("/api/v1/auth/csrf").json()["csrf_token"]
    h = {"X-CSRF-Token": csrf1}
    assert b1.delete(f"/api/v1/auth/sessions/{other['id']}", headers=h).status_code == 204
    assert len(b1.get("/api/v1/auth/sessions").json()) == 2
    assert b1.post("/api/v1/auth/sessions/revoke-others", headers=h).json()["revoked"] == 1
    assert b1.get("/api/v1/me").status_code == 200
    # one was revoked by name, the other in bulk: neither browser is signed in any more
    assert b2.get("/api/v1/me").status_code == 401 and b3.get("/api/v1/me").status_code == 401
    assert len(b1.get("/api/v1/auth/sessions").json()) == 1


def test_one_user_cannot_revoke_another_users_session(site: Callable[..., Site]) -> None:
    s = site()
    org, _ = _seed(s)
    other = make_member(s.c, org, "bob@alpha.example", Role.ANALYST)
    b_ann, _ = s.sign_in("ann@alpha.example")
    ann_session = b_ann.get("/api/v1/auth/sessions").json()[0]["id"]
    r = s.browser().delete(f"/api/v1/auth/sessions/{ann_session}", headers=other.h)
    assert r.status_code == 404
    assert b_ann.get("/api/v1/me").status_code == 200


def test_idle_and_absolute_limits_end_a_session(site: Callable[..., Site]) -> None:
    s = site(SESSION_IDLE_HOURS="1", SESSION_DAYS="1")
    _seed(s)
    browser, _ = s.sign_in("ann@alpha.example")
    assert browser.get("/api/v1/me").status_code == 200
    with s.container.db.session() as db:
        row = db.execute(select(SessionRow)).scalar_one()
        row.last_seen_at = datetime.now(tz=UTC) - timedelta(hours=2)
    assert browser.get("/api/v1/me").status_code == 401  # idle
    b2, _ = s.sign_in("ann@alpha.example")
    with s.container.db.session() as db:
        for row in db.execute(select(SessionRow).where(SessionRow.revoked_at.is_(None))).scalars():
            row.expires_at = datetime.now(tz=UTC) - timedelta(minutes=1)
    assert b2.get("/api/v1/me").status_code == 401  # past its lifetime


def test_removing_a_member_ends_their_browser_session(site: Callable[..., Site]) -> None:
    s = site()
    org, admin_id = _seed(s)
    other = make_member(s.c, org, "bob@alpha.example", Role.ANALYST)
    b_bob, _ = s.sign_in("bob@alpha.example")
    assert b_bob.get("/api/v1/me").status_code == 200
    s.container.accounts.remove_member(org, other.user_id, actor=admin_id)
    assert b_bob.get("/api/v1/me").status_code == 401


def test_only_hashes_of_session_tokens_are_stored(site: Callable[..., Site]) -> None:
    s = site()
    _seed(s)
    browser, _ = s.sign_in("ann@alpha.example")
    raw = browser.cookies.get("ipo_session")
    with s.container.db.session() as db:
        ids = db.execute(select(SessionRow.id)).scalars().all()
    assert raw not in ids and all(len(i) == 64 for i in ids)


def test_switching_organisation_changes_what_the_session_sees(site: Callable[..., Site]) -> None:
    s = site()
    org_a, user = _seed(s)
    acc = s.container.accounts
    org_b = acc.create_org("Beta Advisors")["id"]
    acc.add_member(org_b, user, Role.ANALYST, actor="t")
    browser, _ = s.sign_in("ann@alpha.example")
    csrf = browser.get("/api/v1/auth/csrf").json()["csrf_token"]
    h = {"X-CSRF-Token": csrf}
    browser.post("/api/v1/cases", json={"company_name": "In Alpha"}, headers=h)
    assert browser.get("/api/v1/cases").json()["total"] == 1
    assert (
        browser.post("/api/v1/auth/switch-org", json={"org_id": org_b}, headers=h).status_code
        == 200
    )
    me = browser.get("/api/v1/me").json()
    assert me["org_id"] == org_b and me["role"] == "analyst"
    assert browser.get("/api/v1/cases").json()["total"] == 0
    stranger = acc.create_org("Gamma")["id"]
    refused = browser.post("/api/v1/auth/switch-org", json={"org_id": stranger}, headers=h)
    assert refused.status_code == 422
    assert {o["id"] for o in browser.get("/api/v1/auth/organisations").json()} == {org_a, org_b}
