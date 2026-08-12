"""Signal and signal condition models for strategy outputs."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Signal(Base):
    """Strategy signal/candidate for a symbol."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Strategy run reference
    strategy_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False
    )
    
    # Instrument reference
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Strategy identification
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    strategy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    signal_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    
    # Signal type
    signal_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'candidate', 'watchlist', 'confirmed'
    
    # Price at signal
    price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Ranking
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rank_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Condition summary
    conditions_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conditions_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conditions_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Overall result
    passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    
    # Reasons
    pass_reasons: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array of reasons
    fail_reasons: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array of reasons
    
    # Data timestamps
    data_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_delay_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    conditions: Mapped[list["SignalCondition"]] = relationship(
        "SignalCondition",
        back_populates="signal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "strategy_run_id",
            "token",
            name="uq_signal_run_token",
        ),
        Index("idx_signal_strategy_date", "strategy_name", "signal_date"),
        Index("idx_signal_symbol_date", "symbol", "signal_date"),
        Index("idx_signal_passed", "passed", "signal_date"),
        Index("idx_signal_rank", "strategy_name", "rank", "signal_date"),
    )

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"<Signal(symbol={self.symbol}, strategy={self.strategy_name}, status={status}, rank={self.rank})>"


class SignalCondition(Base):
    """Individual condition evaluation for a signal."""

    __tablename__ = "signal_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Signal reference
    signal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    
    # Condition details
    condition_name: Mapped[str] = mapped_column(String(100), nullable=False)
    condition_description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Evaluation
    passed: Mapped[bool] = mapped_column(nullable=False)
    
    # Values
    expected_value: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )  # Expected condition
    actual_value: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )  # Actual value
    
    # Numeric values for analysis
    numeric_expected: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    numeric_actual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Reason
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Weight/importance
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    
    # Relationships
    signal: Mapped["Signal"] = relationship("Signal", back_populates="conditions")

    __table_args__ = (
        Index("idx_condition_signal", "signal_id"),
        Index("idx_condition_name_passed", "condition_name", "passed"),
    )

    def __repr__(self) -> str:
        status = "✓" if self.passed else "✗"
        return f"<SignalCondition({status} {self.condition_name}: {self.actual_value})>"
