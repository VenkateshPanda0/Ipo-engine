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
from datetime import UTC, date, datetime
from email.utils import format_datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.datastructures import MutableHeaders
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


_DOCS_PATHS = ("/docs", "/redoc")  # only exist outside production; Swagger UI needs its own CDN
HSTS = "max-age=31536000; includeSubDomains"
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
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


class BodyLimitMiddleware:
    """Refuse an oversized request body before it is read into memory (HTTP 413).

    Applies to JSON and other non-upload bodies on POST, PUT and PATCH. A declared Content-Length
    over the limit is refused at once; a body sent in chunks is cut off as soon as it passes the
    limit. Multipart uploads are exempt here because the upload route streams them against its own,
    larger limit (``MAX_UPLOAD_SIZE_MB``).
    """

    def __init__(self, app: Any, max_bytes: int) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        headers = {k: v for k, v in scope["headers"]}
        if headers.get(b"content-type", b"").lower().startswith(b"multipart/form-data"):
            await self.app(scope, receive, send)
            return
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._refuse(scope, receive, send)
            return
        seen = 0

        async def counting_receive() -> Any:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:  # handled as a normal 413 by the app's error handlers
                    raise StarletteHTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE, "Body too large."
                    )
            return message

        await self.app(scope, counting_receive, send)

    async def _refuse(self, scope: Any, receive: Any, send: Any) -> None:
        limit_mb = self.max_bytes / (1024 * 1024)
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": f"The request body is larger than the {limit_mb:g} MB limit.",
                }
            },
            headers={"Cache-Control": "no-store", "Connection": "close"},
        )
        await response(scope, receive, send)


class RequestPlumbingMiddleware:
    """Request id and log line, security headers and v0 deprecation, as one pure ASGI layer.

    Each of these used to be a ``BaseHTTPMiddleware``; every such layer wraps the request and the
    response in extra tasks and streams, which cost a third to half a millisecond per call. Here the
    response headers are adjusted in place as the response starts, which is also when the log line
    is written. Order of effect is unchanged: v0 deprecation, then security headers, then the id.
    """

    def __init__(self, app: Any, settings: Settings) -> None:
        self.app = app
        self.hsts = settings.is_production and settings.trust_https
        self.unauthenticated = settings.allow_unauthenticated and not settings.auth_enabled

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        raw_id = request.headers.get("X-Request-ID", "")
        request_id = raw_id if _REQUEST_ID_RE.match(raw_id) else str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        path = scope["path"]

        async def send_wrapper(message: Any) -> None:
            if message["type"] == "http.response.start":
                self._adjust(request, message, path, request_id, started)
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _adjust(
        self, request: Request, message: Any, path: str, request_id: str, started: float
    ) -> None:
        headers = MutableHeaders(raw=message["headers"])
        message["headers"] = headers.raw

        def default(name: str, value: str) -> None:
            if name not in headers:
                headers[name] = value

        # inner layers first, as before: deprecation, then security headers, then request id
        successor = v0_successor(path)
        if successor is not None:
            headers["Deprecation"] = "true"
            headers["Sunset"] = format_datetime(
                datetime(V0_SUNSET.year, V0_SUNSET.month, V0_SUNSET.day, tzinfo=UTC), usegmt=True
            )
            headers["Link"] = f'<{successor}>; rel="successor-version"'
            logger.warning(
                "deprecated_v0_endpoint",
                extra={
                    "path": path,
                    "method": request.method,
                    "successor": successor,
                    "sunset": V0_SUNSET.isoformat(),
                    "request_id": request_id,
                },
            )
        if not path.startswith(_DOCS_PATHS):
            is_html = headers.get("content-type", "").startswith("text/html")
            default("Content-Security-Policy", CSP_HTML if is_html else CSP_API)
        default("X-Content-Type-Options", "nosniff")
        if not path.startswith(_DOCS_PATHS):
            default("Cache-Control", "no-store")
        if self.hsts:
            default("Strict-Transport-Security", HSTS)
        if self.unauthenticated:
            headers["X-IPO-Engine-Auth"] = "disabled"
        headers["X-Request-ID"] = request_id
        default("Referrer-Policy", "no-referrer")
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "route": route_label(request),
                "principal": getattr(request.state, "principal", "anonymous"),
                "status": message["status"],
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )


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
