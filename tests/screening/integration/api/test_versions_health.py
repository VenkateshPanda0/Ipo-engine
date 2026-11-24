"""The health endpoint shows every version axis (see docs/VERSIONING.md)."""

from typing import Any

from tests.screening.integration.api.test_v1_workflow import _client

import ipo_engine
from ipo_engine.analyze import ANALYSIS_VERSION
from ipo_engine.screening.core.constants import API_VERSION


def test_health_reports_every_version_axis(app_factory: Any) -> None:
    body = _client(app_factory).get("/api/v1/system/health").json()
    assert body["package_version"] == ipo_engine.__version__
    assert body["api_version"] == API_VERSION
    assert body["analysis_version"] == ANALYSIS_VERSION
    assert body["ruleset_version"]
    assert body["version"] == API_VERSION  # the field existing clients already read
