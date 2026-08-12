"""Instrument master model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Instrument(Base):
    """NSE instrument master data."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Angel One identifiers
    token: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    
    # Instrument details
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, default="NSE")
    instrument_type: Mapped[str] = mapped_column(String(20), nullable=False)
    isin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Trading info
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tick_size: Mapped[float] = mapped_column(nullable=False, default=0.05)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Metadata
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_symbol_exchange", "symbol", "exchange"),
        Index("idx_active_instruments", "is_active", "exchange"),
    )

    def __repr__(self) -> str:
        return f"<Instrument(symbol={self.symbol}, token={self.token}, exchange={self.exchange})>"
