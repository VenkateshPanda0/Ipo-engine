"""A small Prometheus exposition: request counts and durations by route template.

Off unless METRICS_ENABLED is set, and then readable by the admin role only. Counters live in memory
in this process (a restart resets them, and several workers each have their own); that is stated in
docs/security.md. Labels are the HTTP method, the route *template* (never the concrete path, so ids
do
not become labels), and the status code. Nothing from a request body or a document is recorded.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from ipo_engine import __version__
from ipo_engine.analyze import ANALYSIS_VERSION
from ipo_engine.screening.api.middleware import route_label
from ipo_engine.screening.core.constants import API_VERSION
from ipo_engine.screening.core.security import Principal, Role, require_role

BUCKETS = (0.005, 0.025, 0.1, 0.5, 2.5, 10.0, 60.0)
METRICS_PATH = "/metrics"
_ADMIN_ONLY = require_role(Role.ADMIN)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Metrics:
    """Thread-safe counters for requests and durations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._buckets: dict[tuple[str, float], int] = defaultdict(int)
        self._sum: dict[str, float] = defaultdict(float)
        self._count: dict[str, int] = defaultdict(int)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, status)] += 1
            self._sum[route] += seconds
            self._count[route] += 1
            for upper in BUCKETS:
                if seconds <= upper:
                    self._buckets[(route, upper)] += 1

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP ipo_http_requests_total HTTP requests handled, by method, route"
                " template and status.",
                "# TYPE ipo_http_requests_total counter",
            ]
            for (method, route, status), n in sorted(self._requests.items()):
                lines.append(
                    "ipo_http_requests_total"
                    f'{{method="{method}",route="{_escape(route)}",status="{status}"}} {n}'
                )
            lines += [
                "# HELP ipo_http_request_duration_seconds Request duration in seconds, by"
                " route template.",
                "# TYPE ipo_http_request_duration_seconds histogram",
            ]
            for route in sorted(self._count):
                r = _escape(route)
                for upper in BUCKETS:
                    n = self._buckets.get((route, upper), 0)
                    lines.append(
                        f'ipo_http_request_duration_seconds_bucket{{route="{r}",le="{upper}"}} {n}'
                    )
                lines.append(
                    "ipo_http_request_duration_seconds_bucket"
                    f'{{route="{r}",le="+Inf"}} {self._count[route]}'
                )
                lines.append(
                    f'ipo_http_request_duration_seconds_sum{{route="{r}"}} {self._sum[route]:.6f}'
                )
                lines.append(
                    f'ipo_http_request_duration_seconds_count{{route="{r}"}} {self._count[route]}'
                )
            lines += [
                "# HELP ipo_build_info Versions of this build (value is always 1).",
                "# TYPE ipo_build_info gauge",
                f'ipo_build_info{{version="{__version__}",api_version="{API_VERSION}",'
                f'analysis_version="{ANALYSIS_VERSION}"}} 1',
            ]
        return "\n".join(lines) + "\n"


def install_metrics(app: FastAPI) -> Metrics:
    """Record every request (except the scrape itself) and serve ``/metrics`` to admins."""
    metrics = Metrics()

    @app.middleware("http")
    async def record(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        import time

        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path != METRICS_PATH:
            metrics.observe(
                request.method,
                route_label(request),
                response.status_code,
                time.perf_counter() - started,
            )
        return response

    @app.get(METRICS_PATH, include_in_schema=False, response_class=PlainTextResponse)
    def scrape(_p: Principal = Depends(_ADMIN_ONLY)) -> PlainTextResponse:
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    return metrics
