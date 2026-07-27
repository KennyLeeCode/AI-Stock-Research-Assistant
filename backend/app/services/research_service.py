"""AI research report generation.

The model's only job is interpretation. It receives a read-only JSON block of
figures already computed by the market-data provider and the indicator service,
and returns prose. Four independent mechanisms keep it from producing data:

  1. **No tools, no network.** The request declares no tools, so the model
     cannot fetch, browse, or execute anything. Its entire world is the block
     of data assembled here.
  2. **A response schema with no numeric fields.** `ResearchNarrative` is
     strings and lists of strings. Nothing the model returns can be stored,
     charted, or displayed as a measurement.
  3. **Schema enforcement at the API boundary.** The schema is sent as a JSON
     Schema via structured outputs, so a malformed shape cannot come back.
  4. **Independent revalidation.** The parsed result is checked against the same
     Pydantic model on receipt. A report failing either check raises
     `AIResponseValidationError` and is discarded - never partially rendered.

The prompt additionally instructs the model to cite only figures present in the
data block and to say plainly when something is unavailable. Note the honest
limit of that instruction: prose is prose, so a figure quoted inside a sentence
is model-written text, not a validated measurement. That is why no prose figure
is ever parsed back out and treated as data - the numbers the UI renders come
from the typed models, and the narrative sits alongside them.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from app.config import get_settings
from app.core.cache import cache, make_key
from app.core.validation import normalize_ticker
from app.schemas.indicators import TechnicalIndicators
from app.schemas.research import (
    STANDARD_DISCLAIMER,
    DataSourceRef,
    ResearchNarrative,
    ResearchReport,
)
from app.schemas.stock import CompanyOverview, NewsFeed, Quote
from app.services import stock_service
from app.services.indicator_service import compute_indicators
from app.core.exceptions import (
    AIResponseValidationError,
    AIServiceError,
    ConfigurationError,
)

logger = logging.getLogger(__name__)

# How many headlines to include. Enough for context, few enough to keep the
# prompt small and the cost predictable.
NEWS_ITEMS_IN_PROMPT = 8
NEWS_SUMMARY_CHAR_LIMIT = 280


SYSTEM_PROMPT = """\
You are a financial research analyst writing a balanced, factual briefing for a \
retail investor. You will be given a JSON block of market data that has already \
been gathered and calculated. Your job is to interpret it in plain English.

ABSOLUTE RULES - these override any other consideration:

1. Use only the figures present in the DATA block. Do not calculate new figures, \
do not estimate, do not infer values that are absent, and do not rely on \
anything you remember about this company from training. If the data contradicts \
your prior knowledge, the data wins.

2. A null value, or a metric listed under "unavailable", means the figure was \
not available. Say so plainly - for example, "a P/E ratio was not available for \
this company". Never substitute a placeholder, never guess, and never treat a \
missing value as zero.

3. Do not give investment advice. No buy, sell, or hold recommendation. No \
price targets of your own. No statements about what the reader should do. You \
describe and interpret; you do not advise.

4. Be genuinely balanced. The bull case and the bear case must each contain at \
least two substantive, distinct points grounded in the supplied data. Do not pad \
one side to make the other look stronger. If the data is broadly positive, the \
bear case should still identify real risks; if it is broadly negative, the bull \
case should still identify real strengths.

5. The conclusion must be neutral. Summarise the tension between the two cases \
and what would need to be true for either to play out. Do not declare a winner.

6. Write for a non-expert. Explain jargon on first use. Be specific and concise; \
avoid filler and hedging language.

UNITS in the DATA block:
  - "change_percent", "price_change_1m", "price_change_3m", "volatility_30d" \
are percentages: 1.25 means 1.25%.
  - "profit_margin", "operating_margin", "return_on_equity", \
"return_on_assets", "dividend_yield" are fractions: 0.25 means 25%.
  - "market_cap", "revenue_ttm", "gross_profit_ttm", "ebitda" are absolute \
amounts in the reporting currency.
  - "rsi_14" is 0-100. Conventionally above 70 is considered overbought and \
below 30 oversold, but treat that as context, not a signal to act on.\
"""


class _AIClient:
    """Lazily constructed Anthropic client, shared across requests."""

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> anthropic.AsyncAnthropic:
        settings = get_settings()
        if not settings.has_ai_key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is not configured on the server."
            )
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = anthropic.AsyncAnthropic(
                        api_key=settings.anthropic_api_key.get_secret_value(),
                        timeout=120.0,
                        max_retries=2,
                    )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


_ai_client = _AIClient()


async def close_ai_client() -> None:
    """Release the AI client's connections on application shutdown."""
    await _ai_client.aclose()


# ==========================================================================
# Prompt assembly
# ==========================================================================
def _trim(text: str | None, limit: int) -> str | None:
    """Shorten free text for the prompt without changing its meaning."""
    if text is None:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def build_data_block(
    *,
    symbol: str,
    quote: Quote,
    indicators: TechnicalIndicators,
    overview: CompanyOverview,
    news: NewsFeed | None,
) -> dict[str, Any]:
    """Assemble the read-only figures handed to the model.

    Nulls are preserved rather than stripped: the model needs to see that a
    metric is absent so it can say so, instead of quietly omitting the topic.
    """
    quote_block = quote.model_dump(
        include={
            "price", "change", "change_percent", "previous_close",
            "open", "day_high", "day_low", "volume", "latest_trading_day",
        },
        mode="json",
    )

    indicator_block = indicators.model_dump(
        include={
            "sma_20", "sma_50", "rsi_14", "volatility_30d",
            "price_change_1m", "price_change_3m",
            "week_52_high", "week_52_low", "as_of", "data_points_used",
        },
        mode="json",
    )

    fundamentals_block = overview.model_dump(
        include={
            "name", "sector", "industry", "country", "currency", "exchange",
            "market_cap", "pe_ratio", "forward_pe", "peg_ratio",
            "price_to_book", "book_value", "eps", "profit_margin",
            "operating_margin", "return_on_equity", "return_on_assets",
            "revenue_ttm", "gross_profit_ttm", "ebitda", "shares_outstanding",
            "dividend_yield", "dividend_per_share", "beta",
            "week_52_high", "week_52_low", "analyst_target_price",
            "latest_quarter",
        },
        mode="json",
    )

    news_block: list[dict[str, Any]] = []
    if news is not None:
        for article in news.articles[:NEWS_ITEMS_IN_PROMPT]:
            news_block.append(
                {
                    "title": article.title,
                    "source": article.source,
                    "published_at": (
                        article.published_at.isoformat()
                        if article.published_at
                        else None
                    ),
                    "provider_sentiment": article.sentiment_label,
                    "summary": _trim(article.summary, NEWS_SUMMARY_CHAR_LIMIT),
                }
            )

    return {
        "symbol": symbol,
        "company_description": _trim(overview.description, 1200),
        "quote": quote_block,
        "technical_indicators": indicator_block,
        "indicators_unavailable": indicators.unavailable,
        "fundamentals": fundamentals_block,
        "recent_news": news_block,
    }


def _build_user_message(data_block: dict[str, Any]) -> str:
    """Wrap the data block in an unambiguous instruction."""
    # sort_keys keeps the serialization deterministic, so identical inputs
    # produce byte-identical prompts and stay eligible for prompt caching.
    payload = json.dumps(data_block, indent=2, sort_keys=True, default=str)
    return (
        "Write a research briefing for this security using ONLY the data below.\n"
        "Any value that is null, or listed under 'indicators_unavailable', is "
        "genuinely unavailable - state that rather than estimating it.\n\n"
        f"<DATA>\n{payload}\n</DATA>"
    )


# ==========================================================================
# Generation
# ==========================================================================
async def _call_model(data_block: dict[str, Any]) -> ResearchNarrative:
    """Call Claude and return a validated narrative.

    Raises:
        ConfigurationError: If the API key is missing or rejected.
        AIServiceError: If the provider fails or declines the request.
        AIResponseValidationError: If the response fails schema validation.
    """
    settings = get_settings()
    client = await _ai_client.get()

    try:
        response = await client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(data_block)}],
            # Structured outputs: the schema is enforced by the API, not just
            # requested in the prompt.
            output_format=ResearchNarrative,
        )
    except anthropic.AuthenticationError as exc:
        # A rejected key is a server misconfiguration, not a user error.
        raise ConfigurationError(
            "The configured ANTHROPIC_API_KEY was rejected by the AI provider."
        ) from exc
    except anthropic.RateLimitError as exc:
        raise AIServiceError(
            "The AI service is rate limited. Please try again shortly."
        ) from exc
    except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
        raise AIServiceError("The AI service could not be reached.") from exc
    except anthropic.APIStatusError as exc:
        # Log the status only. Response bodies can echo request content.
        logger.error("AI provider returned HTTP %s", exc.status_code)
        raise AIServiceError("The AI service returned an error.") from exc

    # Safety classifiers can decline a request; this arrives as a normal 200.
    if response.stop_reason == "refusal":
        logger.warning("AI provider declined the request for this security.")
        raise AIServiceError(
            "The AI service declined to generate a report for this security."
        )

    if response.stop_reason == "max_tokens":
        # A truncated response cannot be trusted to be complete.
        raise AIResponseValidationError(
            "The AI response was cut short before it was complete."
        )

    narrative = response.parsed_output
    if narrative is None:
        raise AIResponseValidationError(
            "The AI service did not return a parseable report."
        )

    # Independent second validation. `parse()` already validates, but this
    # guarantees the object handed onward satisfies the model regardless of any
    # future change in SDK behaviour.
    try:
        return ResearchNarrative.model_validate(narrative.model_dump())
    except ValidationError as exc:
        logger.error("AI report failed revalidation: %s", exc.error_count())
        raise AIResponseValidationError() from exc


async def generate_report(ticker: str, *, refresh: bool = False) -> ResearchReport:
    """Produce a research report for `ticker`.

    Fetches the underlying datasets, computes indicators, asks the model to
    interpret them, and assembles the result with full provenance.

    Args:
        ticker: Symbol to research.
        refresh: Skip the cached report and generate a new one.

    Returns:
        A validated `ResearchReport`.
    """
    symbol = normalize_ticker(ticker)
    settings = get_settings()
    key = make_key("research", symbol)

    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            logger.debug("cache hit: %s", key)
            # Copy so the caller cannot mutate the cached instance, and mark it
            # so the UI can show when a report was generated versus reused.
            return cached.model_copy(update={"cached": True})

    snapshot = await stock_service.get_snapshot(symbol)
    indicators = compute_indicators(snapshot.history)

    data_block = build_data_block(
        symbol=symbol,
        quote=snapshot.quote,
        indicators=indicators,
        overview=snapshot.overview,
        news=snapshot.news,
    )

    narrative = await _call_model(data_block)

    sources = [
        DataSourceRef(
            dataset="quote",
            provider=snapshot.quote.source,
            retrieved_at=snapshot.quote.retrieved_at,
        ),
        DataSourceRef(
            dataset="price_history",
            provider=snapshot.history.source,
            retrieved_at=snapshot.history.retrieved_at,
        ),
        DataSourceRef(
            dataset="fundamentals",
            provider=snapshot.overview.source,
            retrieved_at=snapshot.overview.retrieved_at,
        ),
    ]
    if snapshot.news is not None:
        sources.append(
            DataSourceRef(
                dataset="news",
                provider=snapshot.news.source,
                retrieved_at=snapshot.news.retrieved_at,
            )
        )

    report = ResearchReport(
        symbol=symbol,
        model=settings.anthropic_model,
        cached=False,
        price_as_of=indicators.as_of,
        data_sources=sources,
        company_summary=narrative.company_summary,
        recent_performance=narrative.recent_performance,
        technical_analysis=narrative.technical_analysis,
        fundamental_analysis=narrative.fundamental_analysis,
        bull_case=narrative.bull_case,
        bear_case=narrative.bear_case,
        risks=narrative.risks,
        catalysts=narrative.catalysts,
        neutral_conclusion=narrative.neutral_conclusion,
        # The model's own disclaimer text is deliberately discarded. Legal
        # wording is fixed and must not vary between generations.
        disclaimer=STANDARD_DISCLAIMER,
    )

    cache.set(key, report, settings.cache_ttl_research)
    logger.info("Generated research report for %s using %s", symbol, settings.anthropic_model)
    return report
