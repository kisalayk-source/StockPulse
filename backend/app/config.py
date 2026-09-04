from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "StockPulse API"
    app_environment: Literal["development", "production", "test"] = "production"
    api_prefix: str = "/api/v1"
    cors_origin: str = "http://localhost:5173"
    cors_origin_regex: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    forecast_rate_limit_per_minute: int = Field(default=30, ge=0, le=10_000)
    forecast_scan_rate_limit_per_minute: int = Field(default=10, ge=0, le=10_000)
    order_rate_limit_per_minute: int = Field(default=30, ge=0, le=10_000)
    prediction_enabled: bool = True
    prediction_rate_limit_per_minute: int = Field(default=30, ge=0, le=10_000)

    database_url: str = "sqlite:///./data/kronos.db"
    dev_auth_bypass: bool = False
    dev_auth_email: str = "dev@stockpulse.local"
    jwt_secret: str = Field(default="dev-only-change-me-jwt-secret-32b", repr=False)
    jwt_expire_minutes: int = Field(default=60 * 24 * 7, ge=5, le=60 * 24 * 365)
    # Valid Fernet key for local/dev; replace in production.
    credentials_encryption_key: str = Field(
        default="Ew-PE79v7whzOuVHD2GJ4YHXIPD-THvZVQ2ItZsmvO8=",
        repr=False,
    )

    alpaca_paper_key: str | None = None
    alpaca_paper_secret: str | None = None
    alpaca_live_key: str | None = None
    alpaca_live_secret: str | None = None
    alpaca_data_feed: str = Field(default="iex", pattern="^(iex|sip|boats|overnight)$")
    alpaca_data_credentials_mode: str = Field(default="paper", pattern="^(paper|live)$")
    finnhub_api_key: str | None = None
    allow_live_trading: bool = False
    live_confirmation_token: str | None = Field(default=None, repr=False)
    allow_short_selling: bool = False
    allow_uncovered_options: bool = False

    kronos_model_id: str = "NeoQuasar/Kronos-small"
    kronos_tokenizer_id: str = "NeoQuasar/Kronos-Tokenizer-base"
    kronos_device: str = "auto"
    kronos_max_context: int = Field(default=512, ge=16, le=512)
    kronos_temperature: float = Field(default=0.6, ge=0.1, le=2.0)
    kronos_sample_count: int = Field(default=5, ge=1, le=16)
    kronos_top_p: float = Field(default=0.9, ge=0.1, le=1.0)
    kronos_eval_folds: int = Field(default=3, ge=0, le=8)
    kronos_eval_context: int = Field(default=32, ge=16, le=256)
    kronos_journal_path: str | None = None

    risk_max_position_pct: float = Field(default=0.10, ge=0.01, le=1.0)
    risk_max_option_debit_pct: float = Field(default=0.05, ge=0.005, le=0.5)
    risk_max_daily_loss_pct: float = Field(default=0.03, ge=0.005, le=0.5)
    risk_max_spread_bps: float = Field(default=80.0, ge=5.0, le=500.0)
    risk_min_adv_shares: float = Field(default=200_000.0, ge=0.0)
    risk_max_gross_pct: float = Field(default=1.5, ge=0.2, le=5.0)

    sec_user_agent: str = "StockPulse contact@example.com"
    sec_enabled: bool = True
    sec_requests_per_second: float = Field(default=8.0, ge=1.0, le=10.0)
    sec_cache_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    sec_score_config_path: str = "backend/configs/sec_accumulation.yaml"
    sec_rate_limit_per_minute: int = Field(default=60, ge=0, le=10_000)
    sec_scan_universe_cap: int = Field(default=100, ge=10, le=500)
    sec_scan_on_startup: bool = False
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    research_llm_enabled: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origin.split(",") if item.strip()]

    def alpaca_configured(self, mode: str) -> bool:
        if mode == "paper":
            return bool(self.alpaca_paper_key and self.alpaca_paper_secret)
        return bool(self.alpaca_live_key and self.alpaca_live_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
