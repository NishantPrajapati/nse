"""Candle data models for daily, weekly, and monthly timeframes."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailyCandle(Base):
    """Daily OHLCV candle data."""

    __tablename__ = "daily_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Instrument reference
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Date
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # OHLCV data
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Derived metrics (calculated on insert/update)
    change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Data quality
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("token", "date", name="uq_daily_token_date"),
        Index("idx_daily_symbol_date", "symbol", "date"),
        Index("idx_daily_date_complete", "date", "is_complete"),
    )

    def __repr__(self) -> str:
        return f"<DailyCandle(symbol={self.symbol}, date={self.date}, close={self.close})>"


class WeeklyCandle(Base):
    """Weekly OHLCV candle data derived from daily candles."""

    __tablename__ = "weekly_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Instrument reference
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Week identification (ISO week, Monday-based)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # OHLCV data
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Derived metrics
    change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Data quality
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trading_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("token", "year", "week", name="uq_weekly_token_year_week"),
        Index("idx_weekly_symbol_date", "symbol", "week_start_date"),
        Index("idx_weekly_complete", "is_complete", "week_start_date"),
    )

    def __repr__(self) -> str:
        return f"<WeeklyCandle(symbol={self.symbol}, year={self.year}, week={self.week}, close={self.close})>"


class MonthlyCandle(Base):
    """Monthly OHLCV candle data derived from daily candles."""

    __tablename__ = "monthly_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Instrument reference
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Month identification
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    month_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    month_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # OHLCV data
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Derived metrics
    change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Data quality
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trading_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("token", "year", "month", name="uq_monthly_token_year_month"),
        Index("idx_monthly_symbol_date", "symbol", "month_start_date"),
        Index("idx_monthly_complete", "is_complete", "month_start_date"),
    )

    def __repr__(self) -> str:
        return f"<MonthlyCandle(symbol={self.symbol}, year={self.year}, month={self.month}, close={self.close})>"
