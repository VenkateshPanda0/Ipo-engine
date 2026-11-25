"""The one public route of the app: open a share link. No sign-in; the token is the credential."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ipo_engine.screening.api.dependencies import Container, get_container
from ipo_engine.screening.api.middleware import CSP_HTML
from ipo_engine.screening.services.documents import RateLimiter

router = APIRouter(prefix="/api/v1", tags=["share"])
_limiter = RateLimiter(60)  # per client address per minute: a token cannot be guessed by hammering


@router.get("/shared/{token}")
def open_share(token: str, request: Request, c: Container = Depends(get_container)) -> Response:
    who = request.client.host if request.client else "unknown"
    if not _limiter.allow(f"share:{who}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests.")
    report_id = c.shares.open(token) if 20 <= len(token) <= 100 else None
    if report_id is None:
        # one answer for unknown, expired and revoked, so a link cannot be probed
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This link is not valid.")
    from uuid import UUID

    html = c.report_service.get_report(UUID(report_id), "html")
    return Response(
        html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": CSP_HTML,
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
