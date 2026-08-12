"""Application configuration using Pydantic settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Application
    app_name: str = "NSE Strategy Alerts"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"
    
    # Database
    database_url: str
    
    # Angel One API
    angel_one_api_key: str
    angel_one_client_id: str
    angel_one_password: str
    angel_one_totp_secret: str
    angel_api_timeout: int = 30
    angel_rate_limit_calls: int = 10
    angel_rate_limit_period: int = 1
    
    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_max_message_length: int = 4096
    telegram_max_symbols_in_message: int = 20
    
    # API Security
    admin_api_key: str
    secret_key: str
    
    # Strategy Scheduling (24-hour format HH:MM)
    vcp_scan_time: str = "18:30"
    rb_daily_scan_time: str = "18:30"
    monthly_scan_time: str = "18:30"
    multibagger_scan_time: str = "18:30"
    fundamental_scan_time: str = "19:00"
    
    # Data Ingestion Schedule
    daily_ingest_time: str = "16:00"
    weekly_ingest_time: str = "16:30"
    monthly_ingest_time: str = "17:00"
    
    # Market Data Settings
    min_price: float = 10.0
    max_price: float = 10000.0
    min_volume: int = 1000
    
    # Scheduler Settings
    enable_scheduler: bool = True
    scheduler_timezone: str = "Asia/Kolkata"
    
    # Strategy Enable/Disable
    enable_vcp_strategy: bool = True
    enable_rb_strategy: bool = True
    enable_multibagger_strategy: bool = True
    enable_fundamental_strategy: bool = True
    
    # Fundamentals Provider
    fundamentals_provider: str = "mock"  # Options: mock, screener, tickertape
    
    # Cache Settings
    instrument_cache_ttl_hours: int = 24
    data_ready_threshold_hours: int = 2
    
    # Alert Settings
    enable_telegram_alerts: bool = True
    alert_batch_size: int = 10
    alert_delay_seconds: int = 2
    telegram_retry_delay: int = 60
    max_data_delay_hours: int = 48
    
    # Performance Settings
    max_concurrent_requests: int = 10
    request_timeout_seconds: int = 30


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
