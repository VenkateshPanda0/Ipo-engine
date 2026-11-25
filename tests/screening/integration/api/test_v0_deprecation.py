"""The legacy v0 endpoints say they are going away, and where to go instead."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import pytest

SUNSET = datetime(2027, 5, 25, tzinfo=UTC)
ID = "00000000-0000-0000-0000-000000000000"


def _link(r: Any) -> str:
    return str(r.headers["Link"])


@pytest.mark.parametrize(
    ("method", "path", "successor"),
    [
        ("get", "/rules", "/api/v1/rules"),
        ("get", "/rules/NO-SUCH-RULE", "/api/v1/rules/NO-SUCH-RULE"),
        ("get", "/health", "/api/v1/system/health"),
        ("get", "/ready", "/api/v1/system/ready"),
        ("get", f"/reports/{ID}", f"/api/v1/reports/{ID}"),
        ("post", f"/reviews/reports/{ID}", f"/api/v1/reports/{ID}/sign-off"),
        ("get", f"/reviews/{ID}", "/api/v1/reports"),
        ("post", "/screen/json", "/api/v1/cases"),
    ],
)
def test_every_v0_endpoint_carries_deprecation_sunset_and_successor(
    app_factory: Any, method: str, path: str, successor: str
) -> None:
    r = getattr(app_factory(), method)(path)  # any status: the headers are on errors too
    assert r.headers["Deprecation"] == "true"
    assert parsedate_to_datetime(r.headers["Sunset"]) == SUNSET
    assert _link(r) == f'<{successor}>; rel="successor-version"'


def test_v1_endpoints_are_not_marked(app_factory: Any) -> None:
    client = app_factory()
    for path in ("/api/v1/system/health", "/api/v1/rules", "/openapi.json"):
        r = client.get(path)
        assert "Deprecation" not in r.headers and "Sunset" not in r.headers, path


def test_each_v0_call_logs_one_warning(app_factory: Any, caplog: pytest.LogCaptureFixture) -> None:
    client = app_factory()
    with caplog.at_level("WARNING", logger="ipo_engine.screening.api"):
        client.get("/rules")
        client.get("/rules")
        client.get("/api/v1/rules")  # v1: no warning
    warnings = [r for r in caplog.records if r.getMessage() == "deprecated_v0_endpoint"]
    assert len(warnings) == 2
    assert warnings[0].path == "/rules" and warnings[0].successor == "/api/v1/rules"  # type: ignore[attr-defined]
    assert warnings[0].sunset == "2027-05-25"  # type: ignore[attr-defined]
