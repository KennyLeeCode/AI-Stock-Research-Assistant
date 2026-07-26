"""FastAPI application factory and entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.database import init_db
from app.services.providers import close_provider
from app.services.research_service import close_ai_client

API_PREFIX = "/api"
APP_VERSION = "0.1.0"


def configure_logging(settings: Settings) -> None:
    """Set up root logging once, at the configured level."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start-up and shut-down work."""
    settings = get_settings()
    logger = logging.getLogger(__name__)

    init_db()

    # Surface missing credentials at boot instead of at first request. These are
    # warnings, not failures: the server should still start so `/api/health` is
    # reachable and the operator can see what is wrong.
    if not settings.has_market_data_key:
        logger.warning(
            "ALPHA_VANTAGE_API_KEY is not set. Market data endpoints will fail."
        )
    if not settings.has_ai_key:
        logger.warning("ANTHROPIC_API_KEY is not set. Research generation will fail.")

    logger.info("%s started in %s mode", settings.app_name, settings.environment)
    try:
        yield
    finally:
        # Release both outbound HTTP connection pools so shutdown is clean and
        # tests do not leak sockets between runs.
        await close_provider()
        await close_ai_client()
        logger.info("%s shutting down", settings.app_name)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        description=(
            "Structured stock research: live quotes, historical prices, "
            "fundamentals, technical indicators, news, and AI-generated "
            "research reports grounded strictly in provider data."
        ),
        lifespan=lifespan,
        # Interactive docs are useful in development and are a needless
        # information disclosure in production.
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if settings.is_development else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    register_exception_handlers(app)

    @app.get(f"{API_PREFIX}/health", tags=["system"])
    def health() -> dict[str, object]:
        """Liveness and readiness probe.

        Reports whether required credentials are present as booleans only —
        never the values themselves.
        """
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": APP_VERSION,
            "environment": settings.environment,
            "dependencies": {
                "market_data_configured": settings.has_market_data_key,
                "ai_configured": settings.has_ai_key,
            },
        }

    # Routers for stocks, research, and the watchlist are mounted in a later
    # phase; they attach here under API_PREFIX.

    return app


app = create_app()
