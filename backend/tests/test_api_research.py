"""AI research service.

The language model is replaced outright - these tests never make a billed call.
What is being verified is the contract around the model: that the response
schema cannot carry a number, that a malformed report is discarded rather than
partially shown, that the disclaimer is fixed server-side, and that the prompt
tells the model which metrics are genuinely unavailable.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.exceptions import AIResponseValidationError, AIServiceError
from app.schemas.research import (
    STANDARD_DISCLAIMER,
    ResearchNarrative,
    ResearchRequest,
)
from app.services import research_service

VALID_NARRATIVE_FIELDS: dict[str, Any] = {
    "company_summary": "A consumer electronics company.",
    "recent_performance": "The shares rose over the period.",
    "technical_analysis": "The price sits above its 50-day average.",
    "fundamental_analysis": "Margins are healthy; a PEG ratio was not available.",
    "bull_case": ["Strong margins", "Large installed base"],
    "bear_case": ["High valuation", "Slowing unit growth"],
    "risks": ["Supply chain concentration"],
    "catalysts": ["Upcoming earnings"],
    "neutral_conclusion": "The two cases hinge on whether growth reaccelerates.",
    "disclaimer": "Model-written disclaimer that must be replaced.",
}


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch):
    """Replace the model call with a deterministic narrative."""

    async def _call_model(_data_block: dict[str, Any]) -> ResearchNarrative:
        return ResearchNarrative(**VALID_NARRATIVE_FIELDS)

    monkeypatch.setattr(research_service, "_call_model", _call_model)


# ==========================================================================
# The structural guarantee
# ==========================================================================
class TestSchemaCannotCarryNumbers:
    """The model is a writer, not a calculator - enforced by the schema."""

    def test_no_numeric_field_exists(self) -> None:
        schema = ResearchNarrative.model_json_schema()
        numeric = [
            name
            for name, spec in schema["properties"].items()
            if spec.get("type") in {"number", "integer"}
            or (
                spec.get("type") == "array"
                and spec.get("items", {}).get("type") in {"number", "integer"}
            )
        ]
        assert numeric == []

    def test_additional_properties_are_forbidden(self) -> None:
        """Stops the model inventing a `price_target` key."""
        assert ResearchNarrative.model_json_schema()["additionalProperties"] is False

    def test_extra_keys_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResearchNarrative(**{**VALID_NARRATIVE_FIELDS, "price_target": 250.0})

    def test_all_ten_fields_are_required(self) -> None:
        assert len(ResearchNarrative.model_json_schema()["required"]) == 10


class TestBalanceIsEnforced:
    """Both sides must be argued - a validation rule, not a polite request."""

    def test_valid_report_is_accepted(self) -> None:
        ResearchNarrative(**VALID_NARRATIVE_FIELDS)

    @pytest.mark.parametrize(
        "patch",
        [
            {"bull_case": []},
            {"bear_case": []},
            {"bull_case": ["only one point"]},
            {"bear_case": ["only one point"]},
            {"risks": []},
            {"catalysts": []},
            {"company_summary": ""},
            {"neutral_conclusion": ""},
        ],
    )
    def test_unbalanced_or_empty_reports_are_rejected(
        self, patch: dict[str, Any]
    ) -> None:
        with pytest.raises(ValidationError):
            ResearchNarrative(**{**VALID_NARRATIVE_FIELDS, **patch})


# ==========================================================================
# Prompt construction
# ==========================================================================
class TestDataBlock:
    async def test_nulls_are_preserved_for_the_model(
        self, client: TestClient, market_data
    ) -> None:
        """The model must be able to tell 'absent' from 'not mentioned'."""
        from app.services import stock_service
        from app.services.indicator_service import compute_indicators

        snapshot = await stock_service.get_snapshot("AAPL")
        indicators = compute_indicators(snapshot.history)

        block = research_service.build_data_block(
            symbol="AAPL",
            quote=snapshot.quote,
            indicators=indicators,
            overview=snapshot.overview,
            news=snapshot.news,
        )

        # The provider does not offer a forward P/E, so it must reach the
        # model as null rather than being quietly dropped or zeroed - the model
        # needs to see that the metric is absent so it can say so.
        assert block["fundamentals"]["forward_pe"] is None
        assert block["fundamentals"]["analyst_target_price"] is None
        assert "indicators_unavailable" in block

    def test_system_prompt_states_the_rules(self) -> None:
        prompt = research_service.SYSTEM_PROMPT.lower()
        for phrase in [
            "use only the figures",
            "do not estimate",
            "no buy, sell, or hold",
            "at least two substantive",
            "conclusion must be neutral",
            "never treat a missing value as zero",
        ]:
            assert phrase in prompt, f"system prompt lost: {phrase!r}"


# ==========================================================================
# Report assembly
# ==========================================================================
class TestReportGeneration:
    async def test_produces_a_full_report(self, market_data, fake_model) -> None:
        report = await research_service.generate_report("AAPL")

        assert report.symbol == "AAPL"
        assert report.cached is False
        assert len(report.bull_case) >= 2
        assert len(report.bear_case) >= 2
        assert report.price_as_of is not None

    async def test_disclaimer_is_replaced_server_side(
        self, market_data, fake_model
    ) -> None:
        """Legal wording must not vary between generations."""
        report = await research_service.generate_report("AAPL")

        assert report.disclaimer == STANDARD_DISCLAIMER
        assert report.disclaimer != VALID_NARRATIVE_FIELDS["disclaimer"]
        assert "not financial advice" in report.disclaimer.lower()

    async def test_provenance_is_attached(self, market_data, fake_model) -> None:
        report = await research_service.generate_report("AAPL")
        datasets = {source.dataset for source in report.data_sources}

        assert {"quote", "price_history", "fundamentals"} <= datasets
        assert all(source.provider for source in report.data_sources)

    async def test_second_call_is_served_from_cache(
        self, market_data, fake_model
    ) -> None:
        first = await research_service.generate_report("AAPL")
        second = await research_service.generate_report("AAPL")

        assert first.cached is False
        assert second.cached is True
        assert second.company_summary == first.company_summary

    async def test_refresh_bypasses_the_cache(self, market_data, fake_model) -> None:
        await research_service.generate_report("AAPL")
        refreshed = await research_service.generate_report("AAPL", refresh=True)
        assert refreshed.cached is False


class TestFailureHandling:
    async def test_malformed_report_is_discarded(
        self, market_data, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unvalidated report is never partially surfaced."""

        async def _bad_model(_block: dict[str, Any]) -> ResearchNarrative:
            raise AIResponseValidationError()

        monkeypatch.setattr(research_service, "_call_model", _bad_model)

        with pytest.raises(AIResponseValidationError):
            await research_service.generate_report("AAPL")

    async def test_provider_failure_propagates(
        self, market_data, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _failing_model(_block: dict[str, Any]) -> ResearchNarrative:
            raise AIServiceError("upstream is down")

        monkeypatch.setattr(research_service, "_call_model", _failing_model)

        with pytest.raises(AIServiceError):
            await research_service.generate_report("AAPL")


# ==========================================================================
# HTTP surface
# ==========================================================================
class TestResearchEndpoint:
    def test_returns_a_report(
        self, client: TestClient, market_data, fake_model
    ) -> None:
        response = client.post("/api/research", json={"ticker": "aapl"})

        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "AAPL"
        assert body["disclaimer"] == STANDARD_DISCLAIMER
        assert len(body["bull_case"]) >= 2
        assert len(body["bear_case"]) >= 2

    def test_invalid_ticker_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/research", json={"ticker": "12345"})
        assert response.status_code == 422

    def test_request_schema_normalizes(self) -> None:
        assert ResearchRequest(ticker="  aapl  ").ticker == "AAPL"

    def test_missing_ai_key_is_503(
        self, client: TestClient, market_data, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pydantic import SecretStr

        from app.config import get_settings

        monkeypatch.setattr(
            get_settings(), "anthropic_api_key", SecretStr("your_key_here")
        )
        response = client.post("/api/research", json={"ticker": "AAPL"})

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "configuration_error"
