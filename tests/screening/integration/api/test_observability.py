"""Request logs carry who/what/how long; LOG_FORMAT picks the format; /metrics is opt-in, admin-only."""

import hashlib
import json
import logging
from typing import Any

import pytest

from ipo_engine.screening.core.logging import JsonFormatter, TextFormatter, make_formatter

KEYS = ",".join(
    f"{u}|{r}|sha256={hashlib.sha256(k.encode()).hexdigest()}"
    for u, r, k in (("ann", "admin", "admin-key"), ("vic", "viewer", "viewer-key"))
)
ADMIN = {"Authorization": "Bearer admin-key"}
VIEWER = {"Authorization": "Bearer viewer-key"}


def _request_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "request"]


# ---- the request log line -------------------------------------------------------------------
def test_a_request_log_line_has_request_principal_route_status_and_duration(
    app_factory: Any, caplog: pytest.LogCaptureFixture
) -> None:
    client = app_factory(API_KEYS=KEYS)
    with caplog.at_level(logging.INFO, logger="ipo_engine.screening.api"):
        client.get("/api/v1/rules/NO-SUCH-RULE", headers={**ADMIN, "X-Request-ID": "req-123"})
    (rec,) = _request_records(caplog)
    assert rec.request_id == "req-123"  # type: ignore[attr-defined]
    assert rec.principal == "ann"  # type: ignore[attr-defined]
    assert rec.route == "/api/v1/rules/{rule_id}"  # type: ignore[attr-defined]  # the template
    assert rec.path == "/api/v1/rules/NO-SUCH-RULE"  # type: ignore[attr-defined]
    assert rec.method == "GET" and rec.status == 404  # type: ignore[attr-defined]
    assert isinstance(rec.duration_ms, float) and rec.duration_ms >= 0  # type: ignore[attr-defined]


def test_an_unauthenticated_request_is_logged_as_anonymous(
    app_factory: Any, caplog: pytest.LogCaptureFixture
) -> None:
    client = app_factory(API_KEYS=KEYS)
    with caplog.at_level(logging.INFO, logger="ipo_engine.screening.api"):
        r = client.get("/api/v1/cases")
    assert r.status_code == 401
    (rec,) = _request_records(caplog)
    assert rec.principal == "anonymous" and rec.status == 401  # type: ignore[attr-defined]


def test_an_unmatched_path_gets_a_bounded_route_label(
    app_factory: Any, caplog: pytest.LogCaptureFixture
) -> None:
    client = app_factory()
    with caplog.at_level(logging.INFO, logger="ipo_engine.screening.api"):
        client.get("/definitely/not/a/route/42")
    (rec,) = _request_records(caplog)
    assert rec.route == "unmatched" and rec.status == 404  # type: ignore[attr-defined]


# ---- LOG_FORMAT ---------------------------------------------------------------------------
def _record(**extra: Any) -> logging.LogRecord:
    rec = logging.LogRecord(
        "ipo_engine.screening.api", logging.INFO, "f.py", 1, "request", (), None
    )
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_json_format_is_one_parseable_object_per_line() -> None:
    line = JsonFormatter().format(_record(request_id="r1", status=200))
    assert "\n" not in line
    assert json.loads(line)["request_id"] == "r1"


def test_text_format_is_human_readable_with_the_same_fields() -> None:
    line = TextFormatter().format(_record(request_id="r1", principal="ann", status=200))
    assert "\n" not in line and "INFO" in line and "request" in line
    assert "request_id=r1" in line and "principal=ann" in line and "status=200" in line


def test_make_formatter_picks_by_name_and_rejects_others() -> None:
    assert isinstance(make_formatter("json"), JsonFormatter)
    assert isinstance(make_formatter("text"), TextFormatter)
    with pytest.raises(ValueError, match="LOG_FORMAT"):
        make_formatter("xml")


def test_settings_reject_an_unknown_log_format(tmp_path: Any) -> None:
    from pydantic import ValidationError

    from ipo_engine.screening.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(LOG_FORMAT="xml")  # type: ignore[arg-type]


# ---- /metrics -----------------------------------------------------------------------------
def test_metrics_do_not_exist_unless_enabled(app_factory: Any) -> None:
    assert app_factory().get("/metrics").status_code == 404


def test_metrics_are_admin_only(app_factory: Any) -> None:
    client = app_factory(METRICS_ENABLED="true", API_KEYS=KEYS)
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers=VIEWER).status_code == 403
    assert client.get("/metrics", headers=ADMIN).status_code == 200


def test_metrics_report_requests_by_route_template_in_prometheus_text(app_factory: Any) -> None:
    client = app_factory(METRICS_ENABLED="true", API_KEYS=KEYS)
    client.get("/api/v1/rules/NO-SUCH-RULE", headers=ADMIN)
    client.get("/api/v1/rules/OTHER-ID", headers=ADMIN)
    client.get("/api/v1/system/health")
    body = client.get("/metrics", headers=ADMIN)
    assert body.headers["content-type"].startswith("text/plain")
    text = body.text
    assert "# TYPE ipo_http_requests_total counter" in text
    assert (
        'ipo_http_requests_total{method="GET",route="/api/v1/rules/{rule_id}",status="404"} 2'
        in text
    )
    assert (
        'ipo_http_requests_total{method="GET",route="/api/v1/system/health",status="200"} 1' in text
    )
    assert "# TYPE ipo_http_request_duration_seconds histogram" in text
    assert 'ipo_http_request_duration_seconds_count{route="/api/v1/rules/{rule_id}"} 2' in text
    assert 'le="+Inf"' in text
    assert "ipo_build_info{" in text and 'analysis_version="' in text
    assert "NO-SUCH-RULE" not in text and "admin-key" not in text  # no ids, no secrets as labels
    assert "/metrics" not in text.replace("# ", "")  # scraping itself is not counted
