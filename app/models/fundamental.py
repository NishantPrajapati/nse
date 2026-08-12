"""Fundamental data model for quarterly and annual metrics."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FundamentalData(Base):
    """Fundamental data for stocks (quarterly and annual metrics)."""

    __tablename__ = "fundamental_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Instrument reference
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Data provider
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Period information
    period_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'quarterly', 'annual', 'ttm'
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    filing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Earnings metrics
    eps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps_diluted: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Revenue metrics
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sales: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Profitability
    net_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ebitda: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Market metrics
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_cap_unit: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # 'crores', 'millions', etc.
    shares_outstanding: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Growth metrics (calculated)
    eps_growth_yoy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps_growth_qoq: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_growth_yoy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_growth_qoq: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps_growth_3y: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # 3-year CAGR
    
    # Valuation ratios
    pe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pb_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Data quality
    is_restated: Mapped[bool] = mapped_column(nullable=False, default=False)
    restatement_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    data_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Raw data
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "token",
            "period_type",
            "fiscal_year",
            "fiscal_quarter",
            "restatement_version",
            name="uq_fundamental_period_version",
        ),
        Index("idx_fundamental_symbol_period", "symbol", "period_end_date"),
        Index("idx_fundamental_provider", "provider", "period_end_date"),
        Index("idx_fundamental_quarter", "fiscal_year", "fiscal_quarter"),
    )

    def __repr__(self) -> str:
        quarter_str = f"Q{self.fiscal_quarter}" if self.fiscal_quarter else "Annual"
        return f"<FundamentalData(symbol={self.symbol}, FY{self.fiscal_year} {quarter_str}, EPS={self.eps})>"
