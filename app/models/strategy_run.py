"""Strategy run model for tracking execution history."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StrategyRun(Base):
    """Strategy execution run tracking."""

    __tablename__ = "strategy_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Strategy identification
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    strategy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Run details
    run_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'scheduled', 'manual', 'backtest'
    signal_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )  # Date for which signals are generated
    
    # Execution tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # 'pending', 'running', 'completed', 'failed', 'data_delayed'
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Results
    symbols_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Data quality
    data_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # Latest data date used
    data_delay_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_completeness: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Percentage of complete data
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Configuration
    config_snapshot: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON snapshot of strategy config
    
    # Metadata
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="scheduler"
    )  # 'scheduler', 'api', 'manual'
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_strategy_run_name_date", "strategy_name", "signal_date"),
        Index("idx_strategy_run_status", "status", "started_at"),
        Index("idx_strategy_run_completed", "completed_at"),
    )

    def __repr__(self) -> str:
        return f"<StrategyRun(strategy={self.strategy_name}, date={self.signal_date}, status={self.status})>"
