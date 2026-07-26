"""Request-scoped context and access logging.

Every request is tagged with an id that appears in three places: the server log
line, the `X-Request-ID` response header, and the body of any 5xx error. When a
user reports "it broke", that id is the difference between finding the exact
traceback in seconds and grepping by timestamp and hoping.

Client-supplied ids are honoured so a reverse proxy or an upstream service can
propagate its own trace id through this application.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"

# Client-supplied ids are truncated: they end up in log lines and response
# headers, and an unbounded value from an untrusted caller is a log-injection
# and header-size problem.
MAX_CLIENT_REQUEST_ID_LENGTH = 64

# Health checks are polled constantly by container orchestrators; logging every
# one buries the requests that matter.
QUIET_PATHS = frozenset({"/api/health"})


def get_request_id(request: Request) -> str | None:
    """Return the id assigned to `request`, if the middleware has run."""
    return getattr(request.state, "request_id", None)


def _sanitize(raw: str) -> str:
    """Keep only characters safe to place in a log line and a header."""
    cleaned = "".join(
        char for char in raw if char.isalnum() or char in "-_"
    )
    return cleaned[:MAX_CLIENT_REQUEST_ID_LENGTH]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, logs the outcome, and echoes the id back."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = _sanitize(incoming) or uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Logged here so the access log records the failure even though the
            # response itself is produced by the outer error handler.
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s %s -> unhandled exception in %.1fms [%s]",
                request.method,
                request.url.path,
                elapsed_ms,
                request_id,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id

        if request.url.path not in QUIET_PATHS:
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(
                level,
                "%s %s -> %d in %.1fms [%s]",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                request_id,
            )

        return response
