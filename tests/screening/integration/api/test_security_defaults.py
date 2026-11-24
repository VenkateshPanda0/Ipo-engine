"""Secure defaults: no unauthenticated production, security headers, key hashing."""

import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.core.security import InsecureConfiguration
from ipo_engine.screening.main import create_app


def _settings(tmp_path: Path, **env: str) -> Settings:
    base = {"DATA_DIR": str(tmp_path / "d"), "DATABASE_URL": f"sqlite:///{tmp_path / 'a.db'}"}
    return Settings(**{**base, **env})  # type: ignore[arg-type]


# ---- the production guard (F4) ------------------------------------------------------------
def test_production_without_keys_refuses_to_start(tmp_path: Path) -> None:
    with pytest.raises(InsecureConfiguration) as err:
        create_app(_settings(tmp_path, APP_ENV="production"), inline_processing=True)
    msg = str(err.value)
    assert "API_KEYS" in msg and "ALLOW_UNAUTHENTICATED" in msg and "ipo keys hash" in msg


def test_production_with_a_key_starts_and_requires_it(tmp_path: Path) -> None:
    key = "sha256=" + hashlib.sha256(b"s3cret").hexdigest()
    settings = _settings(tmp_path, APP_ENV="production", API_KEYS=f"ann|admin|{key}")
    with TestClient(create_app(settings, inline_processing=True)) as client:
        assert client.get("/api/v1/cases").status_code == 401
        ok = client.get("/api/v1/cases", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200
        assert "X-IPO-Engine-Auth" not in ok.headers


def test_production_unauthenticated_needs_the_explicit_flag_and_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(tmp_path, APP_ENV="production", ALLOW_UNAUTHENTICATED="true")
    with caplog.at_level("WARNING"):
        app = create_app(settings, inline_processing=True)
    assert "WITHOUT AUTHENTICATION" in caplog.text
    with TestClient(app) as client:
        r = client.get("/api/v1/cases")
        assert r.status_code == 200  # admin local principal, by explicit choice
        assert r.headers["X-IPO-Engine-Auth"] == "disabled"


def test_development_mode_is_unchanged(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path), inline_processing=True)) as client:
        r = client.get("/api/v1/cases")
        assert r.status_code == 200 and "X-IPO-Engine-Auth" not in r.headers


# ---- headers (F5) -------------------------------------------------------------------------
def test_json_responses_carry_a_closed_csp(app_factory: Any) -> None:
    r = app_factory().get("/api/v1/system/health")
    assert r.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Strict-Transport-Security" not in r.headers


def test_error_responses_carry_it_too(app_factory: Any) -> None:
    r = app_factory().get("/api/v1/cases/not-a-uuid")
    assert r.status_code in (401, 404, 422)
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_hsts_only_in_production_with_trust_https(tmp_path: Path) -> None:
    key = "sha256=" + hashlib.sha256(b"k").hexdigest()
    prod = {"APP_ENV": "production", "API_KEYS": f"a|admin|{key}"}
    with TestClient(create_app(_settings(tmp_path, **prod), inline_processing=True)) as c:
        assert "Strict-Transport-Security" not in c.get("/api/v1/system/health").headers
    with TestClient(
        create_app(_settings(tmp_path, TRUST_HTTPS="true", **prod), inline_processing=True)
    ) as c:
        hsts = c.get("/api/v1/system/health").headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts and "includeSubDomains" in hsts
    with TestClient(
        create_app(_settings(tmp_path, TRUST_HTTPS="true"), inline_processing=True)
    ) as c:  # development: never
        assert "Strict-Transport-Security" not in c.get("/api/v1/system/health").headers


def test_the_html_policy_is_one_shared_constant_with_no_script_allowance() -> None:
    import inspect

    from ipo_engine.screening.api.middleware import CSP_HTML
    from ipo_engine.screening.api.routers import reports, v1

    assert "script" not in CSP_HTML and "default-src 'none'" in CSP_HTML
    assert "img-src data:" in CSP_HTML and "frame-ancestors 'none'" in CSP_HTML
    for module in (reports, v1):  # routes use the constant, not their own copy of a policy
        assert "style-src 'unsafe-inline'\"" not in inspect.getsource(module)


def test_the_report_templates_use_no_script_and_load_nothing() -> None:
    """The CSP above is only honest if the reports really use no script or external resource."""
    templates = Path(__file__).resolve().parents[4] / "src/ipo_engine/screening/reports/templates"
    files = list(templates.glob("*.j2"))
    assert files
    for f in files:
        text = f.read_text()
        for needle in ("<script", "<link", "<img", "<iframe", "@import", "url(", "src="):
            assert needle not in text, (f.name, needle)
