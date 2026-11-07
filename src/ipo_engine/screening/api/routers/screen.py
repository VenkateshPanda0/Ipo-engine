"""Screening endpoints (API v0, kept for backward compatibility)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from ipo_engine.screening.api.dependencies import Container, get_container, get_screening_service
from ipo_engine.screening.api.routers.v1 import _read_limited
from ipo_engine.screening.api.schemas.request_schemas import CompanyDataSchema
from ipo_engine.screening.api.schemas.response_schemas import ScreeningResponse
from ipo_engine.screening.core.security import Principal, require_api_key
from ipo_engine.screening.services.screening_service import ScreeningService

router = APIRouter(
    prefix="/screen", tags=["screening (v0)"], dependencies=[Depends(require_api_key)]
)


@router.post("/json", response_model=ScreeningResponse)
def screen_json(
    request: CompanyDataSchema,
    service: ScreeningService = Depends(get_screening_service),
) -> ScreeningResponse:
    """Screen a company from canonical CompanyData JSON."""
    report = service.screen_json(request.to_domain())
    return ScreeningResponse.from_report(report)


@router.post("/pdf", response_model=ScreeningResponse)
async def screen_pdf(
    file: UploadFile = File(...),
    c: Container = Depends(get_container),
    p: Principal = Depends(require_api_key),
) -> ScreeningResponse:
    """Screen a company from one uploaded PDF (synchronous; prefer /api/v1 cases).

    The file type is established from its bytes, not the declared content type. The
    same per-user upload rate limit as API v1 applies.
    """
    if not c.documents.rate_limiter.allow(p.user_id):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many uploads; try again shortly.",
            headers={"Retry-After": "60"},
        )
    content = await _read_limited(file, c.settings.max_upload_size_bytes)
    report = await run_in_threadpool(
        c.screening.screen_pdf, file.filename or "uploaded.pdf", content
    )
    return ScreeningResponse.from_report(report)
