"""FastAPI application assembly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ipo_engine.screening.api.dependencies import Container
from ipo_engine.screening.api.metrics import install_metrics
from ipo_engine.screening.api.middleware import (
    deprecation_middleware,
    register_exception_handlers,
    request_id_middleware,
    security_headers_middleware,
)
from ipo_engine.screening.api.routers import (
    accounts,
    auth,
    health,
    reports,
    reviews,
    rules,
    screen,
    share,
    v1,
)
from ipo_engine.screening.core.config import Settings, get_settings
from ipo_engine.screening.core.constants import API_VERSION
from ipo_engine.screening.core.logging import configure_logging
from ipo_engine.screening.core.security import check_production_auth, parse_api_keys


def create_app(
    settings: Settings | None = None,
    *,
    inline_processing: bool = False,
    http: Any = None,
    webhook_sender: Any = None,
) -> FastAPI:
    """Create the application. ``inline_processing`` runs document jobs synchronously (tests)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    parse_api_keys(settings)  # fail fast on malformed API_KEYS
    check_production_auth(settings)  # and on a production start with no authentication
    container = Container.build(
        settings, inline_processing=inline_processing, http=http, webhook_sender=webhook_sender
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        container.startup()
        yield
        container.shutdown()

    app = FastAPI(
        title="IPO Engine",
        description=(
            "Decision-support screening of Indian main-board IPO eligibility against a versioned, "
            "explicitly scoped ruleset. Not legal advice."
        ),
        version=API_VERSION,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
    )
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_credentials=True,
        allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    app.middleware("http")(deprecation_middleware)
    app.middleware("http")(security_headers_middleware(settings))
    app.middleware("http")(request_id_middleware)
    register_exception_handlers(app)
    # The old unversioned routes hold reports with no owner, so accounts mode serves only the
    # organisation-scoped /api/v1 routes (plus health and the public rules).
    legacy = (screen.router, reports.router, reviews.router)
    for router in (health.router, rules.router, *(() if settings.accounts_enabled else legacy)):
        app.include_router(router)
    app.include_router(v1.router)
    app.include_router(accounts.router)
    app.include_router(auth.router)
    app.include_router(share.router)
    if settings.metrics_enabled:
        install_metrics(app)
    return app


app = create_app()
