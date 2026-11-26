"""
API middleware and exception handlers.

All errors use one envelope: ``{"error": {"code", "message", "request_id", "details"?}}``.
Only whitelisted, primitive details are returned; exception internals, stack traces
and file paths are never sent to clients (baseline defect D13).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from email.utils import format_datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.models.exceptions import DomainError

logger = logging.getLogger("ipo_engine.screening.api")
# Content-Security-Policy for what the API serves. JSON and errors load nothing; an HTML report is
# one self-contained page (inline CSS, no script, no external resource, no framing).
CSP_API = "default-src 'none'; frame-ancestors 'none'"
CSP_HTML = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"
# The legacy v0 endpoints are removed on this date (six months after the deprecation was announced,
# 2026-11-25). Until then each one answers as before, with these headers and a warning in the log.
V0_SUNSET = date(2027, 5, 25)
_UUID = r"[^/]+"
# (path pattern, successor under /api/v1), most specific first. {1} is the first captured group.
_V0_SUCCESSORS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), successor)
    for pattern, successor in (
        (rf"^/reviews/reports/({_UUID})/?$", "/api/v1/reports/{1}/sign-off"),
        (r"^/reviews(/.*)?$", "/api/v1/reports"),
        (r"^/screen(/.*)?$", "/api/v1/cases"),
        (rf"^/reports/({_UUID})/?$", "/api/v1/reports/{1}"),
        (rf"^/rules/({_UUID})/?$", "/api/v1/rules/{1}"),
        (r"^/rules/?$", "/api/v1/rules"),
        (r"^/health/?$", "/api/v1/system/health"),
        (r"^/ready/?$", "/api/v1/system/ready"),
    )
)


def v0_successor(path: str) -> str | None:
    """The /api/v1 address that replaces a legacy v0 path, or None if `path` is not a v0 path."""
    if path.startswith("/api/"):
        return None
    for pattern, successor in _V0_SUCCESSORS:
        m = pattern.match(path)
        if m:
            return successor.replace("{1}", m.group(1) if m.groups() and m.group(1) else "")
    return None


async def deprecation_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Mark legacy v0 responses as deprecated (RFC 8594 Sunset) and log each call."""
    response = await call_next(request)
    successor = v0_successor(request.url.path)
    if successor is not None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = format_datetime(
            datetime(V0_SUNSET.year, V0_SUNSET.month, V0_SUNSET.day, tzinfo=UTC), usegmt=True
        )
        response.headers["Link"] = f'<{successor}>; rel="successor-version"'
        logger.warning(
            "deprecated_v0_endpoint",
            extra={
                "path": request.url.path,
                "method": request.method,
                "successor": successor,
                "sunset": V0_SUNSET.isoformat(),
                "request_id": _request_id(request),
            },
        )
    return response


_DOCS_PATHS = ("/docs", "/redoc")  # only exist outside production; Swagger UI needs its own CDN
HSTS = "max-age=31536000; includeSubDomains"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_STATUS_BY_CODE = {
    "UNSUPPORTED_DOCUMENT": status.HTTP_501_NOT_IMPLEMENTED,  # kept for API v0 compatibility
    "REPORT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "INVALID_STATE": status.HTTP_409_CONFLICT,
    "CONFLICT": status.HTTP_409_CONFLICT,
    "DOCUMENT_REJECTED": 422,
}


def route_label(request: Request) -> str:
    """The matched route's path template (``/api/v1/cases/{case_id}``), or ``unmatched``."""
    path = getattr(request.scope.get("route"), "path", None)
    return str(path) if path else "unmatched"


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def error_response(
    request: Request, status_code: int, code: str, message: str, details: Any = None
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": _request_id(request)}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=jsonable_encoder({"error": body}))


def security_headers_middleware(
    settings: Settings,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Security headers on every response, chosen once from the settings."""
    hsts = settings.is_production and settings.trust_https
    unauthenticated = settings.allow_unauthenticated and not settings.auth_enabled

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith(_DOCS_PATHS):
            is_html = response.headers.get("content-type", "").startswith("text/html")
            response.headers.setdefault("Content-Security-Policy", CSP_HTML if is_html else CSP_API)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if not request.url.path.startswith(_DOCS_PATHS):
            # Nothing this API returns is for a shared cache: lists of people, tokens, exports and
            # other organisations' data must not be kept by a browser, proxy or CDN.
            response.headers.setdefault("Cache-Control", "no-store")
        if hsts:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        if unauthenticated:
            response.headers["X-IPO-Engine-Auth"] = "disabled"
        return response

    return middleware


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach a validated X-Request-ID and log one structured line per request."""
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if _REQUEST_ID_RE.match(incoming) else str(uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "route": route_label(request),
            "principal": getattr(request.state, "principal", "anonymous"),
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return response


def combined_middleware(
    settings: Settings,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Request id and log line, security headers and v0 deprecation as ONE middleware layer.

    Each of the three used to be its own ``BaseHTTPMiddleware``; every such layer re-wraps the
    request and the response, which cost about a third of a millisecond each on every call. They
    behave exactly as before, in the same order (request id outermost, deprecation innermost).
    """
    security = security_headers_middleware(settings)

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        async def after_security(req: Request) -> Response:
            return await deprecation_middleware(req, call_next)

        async def after_request_id(req: Request) -> Response:
            return await security(req, after_security)

        return await request_id_middleware(request, after_request_id)

    return middleware


def register_exception_handlers(app: FastAPI) -> None:
    """Register the standard error envelope handlers."""

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        code = exc.error_code
        http_status = getattr(exc, "http_status", None) or _STATUS_BY_CODE.get(code, 422)
        return error_response(
            request,
            http_status,
            code,
            exc.message,
            exc.public_details(),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "loc": [str(p) for p in err.get("loc", ())],
                "msg": str(err.get("msg", "")),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return error_response(
            request, 422, "VALIDATION_ERROR", "Request validation failed.", details
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        details = [
            {
                "loc": [str(p) for p in err.get("loc", ())],
                "msg": str(err.get("msg", "")),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return error_response(request, 422, "VALIDATION_ERROR", "Data validation failed.", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
            429: "RATE_LIMITED",
        }.get(exc.status_code, "HTTP_ERROR")
        response = error_response(request, exc.status_code, code, str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"request_id": _request_id(request)})
        return error_response(
            request,
            500,
            "INTERNAL_ERROR",
            "An internal error occurred. Quote the request ID when reporting it.",
        )
