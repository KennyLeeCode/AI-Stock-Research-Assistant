"""Application configuration.

All settings are read from environment variables (or `backend/.env`).
Secrets are wrapped in `SecretStr` so they are never revealed by
`repr()`, logging, or an accidental `print(settings)`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Typed application settings.

    Field names are matched to environment variables case-insensitively,
    so `app_name` is populated from `APP_NAME`.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Application ----------
    app_name: str = "AI Stock Research Assistant"
    environment: str = "development"
    log_level: str = "INFO"

    # ---------- Database ----------
    database_url: str = "sqlite:///./stock_research.db"

    # ---------- Market data provider ----------
    # Selects which implementation `get_provider()` builds.
    market_data_provider: str = "fmp"

    # Financial Modeling Prep. The `/stable` API - the older `/api/v3` routes
    # are retired and answer 403.
    fmp_api_key: SecretStr = SecretStr("")
    fmp_base_url: str = "https://financialmodelingprep.com/stable"

    # Alpha Vantage remains supported; set MARKET_DATA_PROVIDER=alpha_vantage.
    alpha_vantage_api_key: SecretStr = SecretStr("")
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"

    # ---------- AI provider ----------
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-opus-5"
    anthropic_max_tokens: int = 8000

    # ---------- Outbound HTTP behaviour ----------
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 2

    # ---------- Cache TTLs (seconds) ----------
    cache_ttl_quote: int = 60
    cache_ttl_history: int = 3600
    cache_ttl_overview: int = 86400
    cache_ttl_news: int = 900
    cache_ttl_research: int = 3600

    # ---------- CORS ----------
    # Stored as a raw comma-separated string; see `cors_origins_list`.
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}")
        return normalized

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS origins parsed from the comma-separated env value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        """True when the configured database is SQLite."""
        return self.database_url.startswith("sqlite")

    @property
    def is_development(self) -> bool:
        return self.environment.strip().lower() == "development"

    @property
    def has_fmp_key(self) -> bool:
        return _is_real_secret(self.fmp_api_key)

    @property
    def has_alpha_vantage_key(self) -> bool:
        return _is_real_secret(self.alpha_vantage_api_key)

    @property
    def market_data_key(self) -> SecretStr:
        """The API key belonging to the selected provider."""
        if self.market_data_provider.strip().lower() == "alpha_vantage":
            return self.alpha_vantage_api_key
        return self.fmp_api_key

    @property
    def has_market_data_key(self) -> bool:
        """Whether the *selected* provider has a usable key.

        Used by the health endpoint and the startup warning. Individual
        providers check their own key instead, so that constructing one
        directly does not depend on which provider happens to be selected.
        """
        return _is_real_secret(self.market_data_key)

    @property
    def has_ai_key(self) -> bool:
        return _is_real_secret(self.anthropic_api_key)


def _is_real_secret(secret: SecretStr) -> bool:
    """True if `secret` holds a genuine value rather than a template default.

    Copying `.env.example` to `.env` leaves values like
    `your_anthropic_key_here` in place. Treating those as configured would make
    `/api/health` report success and push the failure to the first real request,
    where it surfaces as a confusing upstream auth error instead of an obvious
    "you forgot to set your key".
    """
    value = secret.get_secret_value().strip()
    if not value:
        return False
    lowered = value.lower()
    return not (lowered.startswith("your_") or lowered.endswith("_here"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so the `.env` file is parsed exactly once. Used as a FastAPI
    dependency and imported directly by services.
    """
    return Settings()
