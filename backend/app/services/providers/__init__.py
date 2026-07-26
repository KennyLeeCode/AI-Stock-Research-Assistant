"""Market-data provider registry.

`get_provider()` returns the process-wide provider selected by the
`MARKET_DATA_PROVIDER` setting. Adding a provider means writing a
`StockDataProvider` subclass and adding one entry to `_PROVIDERS`.
"""

from __future__ import annotations

from collections.abc import Callable

from app.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.services.providers.alpha_vantage import AlphaVantageProvider
from app.services.providers.base import StockDataProvider

_PROVIDERS: dict[str, Callable[[Settings], StockDataProvider]] = {
    "alpha_vantage": AlphaVantageProvider,
}

_instance: StockDataProvider | None = None


def get_provider() -> StockDataProvider:
    """Return the configured provider singleton.

    A single instance is reused so the underlying HTTP connection pool is
    shared across requests rather than rebuilt per call.
    """
    global _instance
    if _instance is None:
        settings = get_settings()
        key = settings.market_data_provider.strip().lower()
        factory = _PROVIDERS.get(key)
        if factory is None:
            raise ConfigurationError(
                f"Unknown MARKET_DATA_PROVIDER {settings.market_data_provider!r}. "
                f"Supported values: {', '.join(sorted(_PROVIDERS))}."
            )
        _instance = factory(settings)
    return _instance


async def close_provider() -> None:
    """Close the provider's network resources on application shutdown."""
    global _instance
    if _instance is not None:
        await _instance.aclose()
        _instance = None


__all__ = [
    "StockDataProvider",
    "AlphaVantageProvider",
    "get_provider",
    "close_provider",
]
