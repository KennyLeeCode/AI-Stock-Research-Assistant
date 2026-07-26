"""Domain exceptions and their FastAPI handlers.

Every error the application raises deliberately is an `AppError`. Each one
carries an HTTP status, a stable machine-readable `code` for the frontend to
branch on, and a human-readable message that is safe to show a user.

Anything *not* an `AppError` is treated as a bug: it is logged with a full
traceback server-side and returned to the client as a generic 500, so internal
details and provider URLs (which may contain API keys) never leak.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------
class AppError(Exception):
    """Base class for all deliberately raised application errors."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the JSON body returned to the client."""
        payload: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


# --------------------------------------------------------------------------
# Client / input errors
# --------------------------------------------------------------------------
class InvalidTickerError(AppError):
    """The supplied ticker symbol is not a plausible symbol."""

    status_code = 400
    code = "invalid_ticker"
    message = "The ticker symbol is not valid."


class TickerNotFoundError(AppError):
    """The symbol is well-formed but the data provider has no such security."""

    status_code = 404
    code = "ticker_not_found"
    message = "No data was found for that ticker symbol."


class ResourceNotFoundError(AppError):
    """A requested stored resource (e.g. a watchlist entry) does not exist."""

    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class DuplicateResourceError(AppError):
    """The resource already exists and cannot be created twice."""

    status_code = 409
    code = "duplicate_resource"
    message = "That resource already exists."


# --------------------------------------------------------------------------
# Upstream market-data provider errors
# --------------------------------------------------------------------------
class ProviderError(AppError):
    """The upstream market-data provider failed in an unexpected way."""

    status_code = 502
    code = "provider_error"
    message = "The market data provider returned an unexpected response."


class ProviderTimeoutError(ProviderError):
    """The upstream provider did not respond within the configured timeout."""

    status_code = 504
    code = "provider_timeout"
    message = "The market data provider timed out. Please try again."


class ProviderRateLimitError(ProviderError):
    """The upstream provider's rate limit or daily quota was exhausted."""

    status_code = 429
    code = "provider_rate_limited"
    message = (
        "The market data provider's rate limit was reached. "
        "Please wait a moment and try again."
    )


# --------------------------------------------------------------------------
# Data-integrity errors
# --------------------------------------------------------------------------
class InsufficientDataError(AppError):
    """Not enough real data exists to compute what was asked for.

    Raised instead of substituting a default, padding a series, or estimating a
    value. Financial figures are either measured from provider data or absent —
    they are never invented.
    """

    status_code = 422
    code = "insufficient_data"
    message = "There is not enough historical data to compute this result."


# --------------------------------------------------------------------------
# AI provider errors
# --------------------------------------------------------------------------
class AIServiceError(AppError):
    """The AI provider call failed."""

    status_code = 502
    code = "ai_service_error"
    message = "The AI research service is temporarily unavailable."


class AIResponseValidationError(AIServiceError):
    """The AI returned a payload that failed Pydantic validation.

    The report is discarded rather than partially surfaced: an unvalidated
    research report is not shown to the user under any circumstances.
    """

    status_code = 502
    code = "ai_response_invalid"
    message = "The AI research service returned a malformed report."


class ConfigurationError(AppError):
    """A required setting (such as an API key) is missing."""

    status_code = 503
    code = "configuration_error"
    message = "The server is not configured to serve this request."


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Render an `AppError` as its declared status code and JSON payload."""
    log = logger.warning if exc.status_code < 500 else logger.error
    log("%s (%s): %s", type(exc).__name__, exc.code, exc.message, extra={"details": exc.details})
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render FastAPI request-validation failures in our error envelope."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request was rejected by input validation.",
                "details": {"errors": exc.errors()},
            }
        },
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Catch-all. Logs the traceback; returns no internal detail to the client."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all error handlers to the application."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
