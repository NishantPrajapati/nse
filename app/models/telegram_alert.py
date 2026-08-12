"""Telegram alert model for tracking message delivery."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TelegramAlert(Base):
    """Telegram alert delivery tracking with deduplication."""

    __tablename__ = "telegram_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Strategy run reference
    strategy_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False
    )
    
    # Deduplication key components
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    strategy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    signal_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'summary', 'individual', 'health'
    
    # Symbol (for individual alerts, null for summary)
    symbol: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    
    # Message details
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_length: Mapped[int] = mapped_column(Integer, nullable=False)
    has_attachment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attachment_filename: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Delivery tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # 'pending', 'sent', 'failed', 'retrying'
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    
    # Telegram response
    telegram_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_response: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON response
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timing
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "strategy_name",
            "strategy_version",
            "signal_date",
            "alert_type",
            "symbol",
            name="uq_telegram_alert_dedup",
        ),
        Index("idx_telegram_alert_status", "status", "scheduled_at"),
        Index("idx_telegram_alert_retry", "status", "next_retry_at"),
        Index("idx_telegram_alert_strategy_date", "strategy_name", "signal_date"),
    )

    def __repr__(self) -> str:
        symbol_str = f" {self.symbol}" if self.symbol else ""
        return f"<TelegramAlert({self.strategy_name}{symbol_str}, status={self.status}, attempts={self.attempt_count})>"
