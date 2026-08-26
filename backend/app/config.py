from functools import lru_cache
from pathlib import Path

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
    api_prefix: str = "/api/v1"
    cors_origin: str = "http://localhost:5173"
    cors_origin_regex: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    forecast_rate_limit_per_minute: int = Field(default=30, ge=0, le=10_000)
    forecast_scan_rate_limit_per_minute: int = Field(default=10, ge=0, le=10_000)
    order_rate_limit_per_minute: int = Field(default=30, ge=0, le=10_000)

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
