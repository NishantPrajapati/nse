"""Base strategy class for all screening strategies."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.signal import Signal, SignalCondition
from app.models.strategy_run import StrategyRun

logger = get_logger(__name__)


class StrategyCondition:
    """Represents a single strategy condition evaluation."""

    def __init__(
        self,
        name: str,
        description: str,
        passed: bool,
        expected_value: Optional[str] = None,
        actual_value: Optional[str] = None,
        numeric_expected: Optional[float] = None,
        numeric_actual: Optional[float] = None,
        reason: Optional[str] = None,
        weight: float = 1.0,
    ):
        """
        Initialize strategy condition.
        
        Args:
            name: Condition name
            description: Condition description
            passed: Whether condition passed
            expected_value: Expected value (string representation)
            actual_value: Actual value (string representation)
            numeric_expected: Expected value (numeric)
            numeric_actual: Actual value (numeric)
            reason: Reason for pass/fail
            weight: Condition weight/importance
        """
        self.name = name
        self.description = description
        self.passed = passed
        self.expected_value = expected_value
        self.actual_value = actual_value
        self.numeric_expected = numeric_expected
        self.numeric_actual = numeric_actual
        self.reason = reason
        self.weight = weight


class StrategyResult:
    """Represents the result of strategy evaluation for a symbol."""

    def __init__(
        self,
        symbol: str,
        token: str,
        passed: bool,
        conditions: list[StrategyCondition],
        price: float,
        volume: int,
        rank_score: float = 0.0,
        data_date: Optional[datetime] = None,
    ):
        """
        Initialize strategy result.
        
        Args:
            symbol: Stock symbol
            token: Symbol token
            passed: Whether all conditions passed
            conditions: List of condition evaluations
            price: Current price
            volume: Current volume
            rank_score: Ranking score
            data_date: Date of data used
        """
        self.symbol = symbol
        self.token = token
        self.passed = passed
        self.conditions = conditions
        self.price = price
        self.volume = volume
        self.rank_score = rank_score
        self.data_date = data_date or datetime.utcnow()
        
        # Calculate condition statistics
        self.conditions_total = len(conditions)
        self.conditions_passed = sum(1 for c in conditions if c.passed)
        self.conditions_failed = self.conditions_total - self.conditions_passed
        
        # Generate reasons
        self.pass_reasons = [
            c.reason or c.name for c in conditions if c.passed and c.reason
        ]
        self.fail_reasons = [
            c.reason or c.name for c in conditions if not c.passed
        ]


class BaseStrategy(ABC):
    """Abstract base class for all screening strategies."""

    def __init__(
        self,
        strategy_name: str,
        strategy_version: str,
        description: str,
    ):
        """
        Initialize strategy.
        
        Args:
            strategy_name: Strategy name
            strategy_version: Strategy version
            description: Strategy description
        """
        self.strategy_name = strategy_name
        self.strategy_version = strategy_version
        self.description = description
        logger.info(
            "Strategy initialized",
            strategy=strategy_name,
            version=strategy_version,
        )

    @abstractmethod
    async def evaluate(
        self,
        db: AsyncSession,
        symbol: str,
        token: str,
    ) -> StrategyResult:
        """
        Evaluate strategy for a symbol.
        
        Args:
            db: Database session
            symbol: Stock symbol
            token: Symbol token
            
        Returns:
            Strategy evaluation result
        """
        pass

    @abstractmethod
    def get_required_data(self) -> dict[str, Any]:
        """
        Get required data specifications.
        
        Returns:
            Dictionary specifying required data:
            {
                'daily_candles': {'days': 200},
                'weekly_candles': {'weeks': 52},
                'monthly_candles': {'months': 24},
                'fundamentals': True,
            }
        """
        pass

    @abstractmethod
    def get_schedule(self) -> dict[str, Any]:
        """
        Get strategy schedule configuration.
        
        Returns:
            Dictionary with schedule details:
            {
                'frequency': 'daily' | 'weekly' | 'monthly',
                'time': '16:00',
                'requires_data_ready': True,
                'requires_complete_candles': ['daily', 'weekly', 'monthly'],
            }
        """
        pass

    def rank_results(
        self,
        results: list[StrategyResult],
    ) -> list[StrategyResult]:
        """
        Rank strategy results.
        
        Args:
            results: List of strategy results
            
        Returns:
            Ranked list of results (highest rank first)
        """
        # Sort by rank_score descending
        sorted_results = sorted(
            results,
            key=lambda r: r.rank_score,
            reverse=True,
        )
        
        # Assign rank numbers
        for i, result in enumerate(sorted_results, start=1):
            result.rank = i
        
        return sorted_results

    async def save_signal(
        self,
        db: AsyncSession,
        strategy_run: StrategyRun,
        result: StrategyResult,
        signal_type: str = "candidate",
    ) -> Signal:
        """
        Save strategy result as a signal.
        
        Args:
            db: Database session
            strategy_run: Strategy run instance
            result: Strategy result
            signal_type: Signal type ('candidate', 'watchlist', 'confirmed')
            
        Returns:
            Created signal
        """
        # Get instrument_id
        from app.models.instrument import Instrument
        from sqlalchemy import select
        
        instr_result = await db.execute(
            select(Instrument).where(Instrument.token == result.token)
        )
        instrument = instr_result.scalar_one()
        
        # Create signal
        signal = Signal(
            strategy_run_id=strategy_run.id,
            instrument_id=instrument.id,
            token=result.token,
            symbol=result.symbol,
            strategy_name=self.strategy_name,
            strategy_version=self.strategy_version,
            signal_date=strategy_run.signal_date,
            signal_type=signal_type,
            price=result.price,
            volume=result.volume,
            rank=getattr(result, 'rank', 0),
            rank_score=result.rank_score,
            conditions_total=result.conditions_total,
            conditions_passed=result.conditions_passed,
            conditions_failed=result.conditions_failed,
            passed=result.passed,
            pass_reasons=str(result.pass_reasons) if result.pass_reasons else None,
            fail_reasons=str(result.fail_reasons) if result.fail_reasons else None,
            data_date=result.data_date,
        )
        
        db.add(signal)
        await db.flush()
        
        # Save individual conditions
        for condition in result.conditions:
            signal_condition = SignalCondition(
                signal_id=signal.id,
                condition_name=condition.name,
                condition_description=condition.description,
                passed=condition.passed,
                expected_value=condition.expected_value,
                actual_value=condition.actual_value,
                numeric_expected=condition.numeric_expected,
                numeric_actual=condition.numeric_actual,
                reason=condition.reason,
                weight=condition.weight,
            )
            db.add(signal_condition)
        
        await db.flush()
        
        logger.debug(
            "Signal saved",
            symbol=result.symbol,
            strategy=self.strategy_name,
            passed=result.passed,
            conditions_passed=result.conditions_passed,
        )
        
        return signal

    def get_strategy_info(self) -> dict[str, Any]:
        """
        Get strategy information.
        
        Returns:
            Strategy metadata
        """
        return {
            "name": self.strategy_name,
            "version": self.strategy_version,
            "description": self.description,
            "required_data": self.get_required_data(),
            "schedule": self.get_schedule(),
        }

    def calculate_rank_score(
        self,
        conditions: list[StrategyCondition],
        **kwargs
    ) -> float:
        """
        Calculate ranking score based on conditions.
        
        Args:
            conditions: List of evaluated conditions
            **kwargs: Additional parameters for scoring
            
        Returns:
            Rank score (higher is better)
        """
        # Default scoring: weighted sum of passed conditions
        total_weight = sum(c.weight for c in conditions)
        passed_weight = sum(c.weight for c in conditions if c.passed)
        
        if total_weight == 0:
            return 0.0
        
        base_score = (passed_weight / total_weight) * 100
        
        # Bonus for passing all conditions
        if all(c.passed for c in conditions):
            base_score += 10
        
        return base_score
