"""AI research report endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.research import ResearchReport, ResearchRequest
from app.services import research_service

router = APIRouter(tags=["research"])


@router.post(
    "/research",
    response_model=ResearchReport,
    summary="Generate an AI research report",
    responses={
        422: {"description": "The ticker is malformed, or history is too short."},
        429: {"description": "The market data provider's quota was reached."},
        502: {
            "description": (
                "The market data or AI provider failed, or the AI returned a "
                "report that failed validation and was discarded."
            )
        },
        503: {"description": "The server is missing a required API key."},
        504: {"description": "A provider did not respond in time."},
    },
)
async def create_research_report(payload: ResearchRequest) -> ResearchReport:
    """Generate a balanced research briefing for a ticker.

    The report is assembled from data this API has already fetched and computed:
    the quote, price history, technical indicators, fundamentals, and recent
    headlines. The language model receives that data as a read-only block and
    returns prose only — every figure shown in the UI comes from the typed
    market-data models, not from the model's output.

    Reports are cached briefly. Set `refresh` to `true` to force a new one.
    """
    return await research_service.generate_report(
        payload.ticker, refresh=payload.refresh
    )
