"""Multi-bagger Technical strategy implementation."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.candle import DailyCandle, MonthlyCandle
from app.strategies.base_strategy import (
    BaseStrategy,
    StrategyCondition,
    StrategyResult,
)

logger = get_logger(__name__)


class MultibaggerTechnicalStrategy(BaseStrategy):
    """
    Multi-bagger Technical Strategy.
    
    Conditions (month-end only):
    1. Completed monthly % change >= 20%
    2. Completed monthly RSI(14) >= 50
    3. Monthly EMA10 >= Monthly EMA20
    4. Daily EMA(volume, 30) >= 50,000
    5. Close >= ₹20
    6. AND either:
       a. At least one monthly EMA10 cross above EMA20 in last 20 completed months, OR
       b. Completed monthly close crossed above monthly EMA10
    """

    def __init__(self):
        """Initialize Multi-bagger Technical strategy."""
        super().__init__(
            strategy_name="MultibaggerTechnical",
            strategy_version="1.0",
            description="Multi-bagger Technical - Identifies strong monthly momentum with EMA crossovers",
        )

    def calculate_rsi(self, closes: list[float], period: int = 14) -> float:
        """
        Calculate Relative Strength Index.
        
        Args:
            closes: List of closing prices
            period: RSI period
            
        Returns:
            RSI value
        """
        if len(closes) < period + 1:
            return 50.0  # Neutral if insufficient data
        
        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Separate gains and losses
        gains = [max(0, change) for change in changes]
        losses = [abs(min(0, change)) for change in changes]
        
        # Calculate average gain and loss
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi

    def calculate_ema(self, values: list[float], period: int) -> list[float]:
        """
        Calculate Exponential Moving Average.
        
        Args:
            values: List of values
            period: EMA period
            
        Returns:
            List of EMA values
        """
        if len(values) < period:
            return []
        
        ema_values = []
        multiplier = 2 / (period + 1)
        
        # Initial EMA is simple average
        initial_ema = sum(values[:period]) / period
        ema_values.append(initial_ema)
        
        # Calculate subsequent EMAs
        for value in values[period:]:
            new_ema = (value * multiplier) + (ema_values[-1] * (1 - multiplier))
            ema_values.append(new_ema)
        
        return ema_values

    def detect_ema_crossover(
        self,
        ema_short: list[float],
        ema_long: list[float],
    ) -> bool:
        """
        Detect if EMA short crossed above EMA long.
        
        Args:
            ema_short: Short EMA values
            ema_long: Long EMA values
            
        Returns:
            True if crossover detected
        """
        if len(ema_short) < 2 or len(ema_long) < 2:
            return False
        
        # Check for crossover in any period
        for i in range(1, min(len(ema_short), len(ema_long))):
            # Previous: short <= long, Current: short > long
            if ema_short[i-1] <= ema_long[i-1] and ema_short[i] > ema_long[i]:
                return True
        
        return False

    async def evaluate(
        self,
        db: AsyncSession,
        symbol: str,
        token: str,
    ) -> StrategyResult:
        """
        Evaluate Multi-bagger Technical strategy for a symbol.
        
        Args:
            db: Database session
            symbol: Stock symbol
            token: Symbol token
            
        Returns:
            Strategy evaluation result
        """
        logger.debug("Evaluating Multi-bagger Technical strategy", symbol=symbol)
        
        conditions = []
        
        try:
            # Fetch monthly candles (need 20+ completed)
            result = await db.execute(
                select(MonthlyCandle)
                .where(
                    and_(
                        MonthlyCandle.token == token,
                        MonthlyCandle.is_complete == True,
                    )
                )
                .order_by(MonthlyCandle.month_start_date.desc())
                .limit(25)
            )
            monthly_candles = list(reversed(result.scalars().all()))
            
            if len(monthly_candles) < 20:
                logger.warning(
                    "Insufficient monthly candles for Multi-bagger",
                    symbol=symbol,
                    available=len(monthly_candles),
                )
                return StrategyResult(
                    symbol=symbol,
                    token=token,
                    passed=False,
                    conditions=[
                        StrategyCondition(
                            name="data_availability",
                            description="Sufficient historical data",
                            passed=False,
                            reason=f"Only {len(monthly_candles)} monthly candles, need 20+",
                        )
                    ],
                    price=monthly_candles[-1].close if monthly_candles else 0,
                    volume=0,
                )
            
            latest_monthly = monthly_candles[-1]
            
            # Fetch daily candles for volume EMA
            result = await db.execute(
                select(DailyCandle)
                .where(
                    and_(
                        DailyCandle.token == token,
                        DailyCandle.is_complete == True,
                    )
                )
                .order_by(DailyCandle.date.desc())
                .limit(50)
            )
            daily_candles = list(reversed(result.scalars().all()))
            
            # Condition 1: Completed monthly % change >= 20%
            monthly_change_pct = latest_monthly.change_percent or 0
            strong_monthly_move = monthly_change_pct >= 20
            
            conditions.append(StrategyCondition(
                name="monthly_change",
                description="Monthly % change >= 20%",
                passed=strong_monthly_move,
                expected_value=">= 20%",
                actual_value=f"{monthly_change_pct:.2f}%",
                numeric_expected=20.0,
                numeric_actual=monthly_change_pct,
                reason=f"Monthly gain: {monthly_change_pct:.2f}%" if strong_monthly_move else "Insufficient monthly gain",
                weight=3.0,
            ))
            
            # Condition 2: Completed monthly RSI(14) >= 50
            monthly_closes = [c.close for c in monthly_candles]
            monthly_rsi = self.calculate_rsi(monthly_closes, period=14)
            rsi_bullish = monthly_rsi >= 50
            
            conditions.append(StrategyCondition(
                name="monthly_rsi",
                description="Monthly RSI(14) >= 50",
                passed=rsi_bullish,
                expected_value=">= 50",
                actual_value=f"{monthly_rsi:.2f}",
                numeric_expected=50.0,
                numeric_actual=monthly_rsi,
                reason=f"RSI: {monthly_rsi:.2f}" if rsi_bullish else "RSI below 50",
                weight=2.0,
            ))
            
            # Condition 3: Monthly EMA10 >= Monthly EMA20
            monthly_ema10 = self.calculate_ema(monthly_closes, 10)
            monthly_ema20 = self.calculate_ema(monthly_closes, 20)
            
            if monthly_ema10 and monthly_ema20:
                ema10_val = monthly_ema10[-1]
                ema20_val = monthly_ema20[-1]
                ema_aligned = ema10_val >= ema20_val
                
                conditions.append(StrategyCondition(
                    name="monthly_ema_alignment",
                    description="Monthly EMA10 >= Monthly EMA20",
                    passed=ema_aligned,
                    expected_value=f">= {ema20_val:.2f}",
                    actual_value=f"{ema10_val:.2f}",
                    numeric_expected=ema20_val,
                    numeric_actual=ema10_val,
                    reason="Bullish EMA alignment" if ema_aligned else "EMA10 below EMA20",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="monthly_ema_alignment",
                    description="Monthly EMA10 >= Monthly EMA20",
                    passed=False,
                    reason="Insufficient data for monthly EMA calculation",
                ))
            
            # Condition 4: Daily EMA(volume, 30) >= 50,000
            if len(daily_candles) >= 30:
                daily_volumes = [float(c.volume) for c in daily_candles]
                volume_ema30 = self.calculate_ema(daily_volumes, 30)
                
                if volume_ema30:
                    avg_volume = volume_ema30[-1]
                    volume_filter = avg_volume >= 50000
                    
                    conditions.append(StrategyCondition(
                        name="avg_volume",
                        description="Daily EMA(volume, 30) >= 50,000",
                        passed=volume_filter,
                        expected_value=">= 50,000",
                        actual_value=f"{avg_volume:,.0f}",
                        numeric_expected=50000,
                        numeric_actual=avg_volume,
                        reason=f"Avg volume: {avg_volume:,.0f}",
                        weight=1.5,
                    ))
                else:
                    conditions.append(StrategyCondition(
                        name="avg_volume",
                        description="Daily EMA(volume, 30) >= 50,000",
                        passed=False,
                        reason="Cannot calculate volume EMA",
                    ))
            else:
                conditions.append(StrategyCondition(
                    name="avg_volume",
                    description="Daily EMA(volume, 30) >= 50,000",
                    passed=False,
                    reason=f"Only {len(daily_candles)} daily candles, need 30+",
                ))
            
            # Condition 5: Close >= ₹20
            min_price = 20.0
            price_filter = latest_monthly.close >= min_price
            
            conditions.append(StrategyCondition(
                name="min_price",
                description="Close >= ₹20",
                passed=price_filter,
                expected_value=f">= {min_price}",
                actual_value=f"{latest_monthly.close:.2f}",
                numeric_expected=min_price,
                numeric_actual=latest_monthly.close,
                reason="Meets minimum price" if price_filter else "Below minimum price",
                weight=1.0,
            ))
            
            # Condition 6: EMA crossover or close above EMA10
            crossover_detected = False
            close_above_ema10 = False
            
            if monthly_ema10 and monthly_ema20 and len(monthly_ema10) >= 20:
                # Check for crossover in last 20 months
                crossover_detected = self.detect_ema_crossover(
                    monthly_ema10[-20:],
                    monthly_ema20[-20:],
                )
            
            if monthly_ema10:
                # Check if close crossed above EMA10
                ema10_current = monthly_ema10[-1]
                if len(monthly_ema10) >= 2:
                    ema10_prev = monthly_ema10[-2]
                    prev_close = monthly_closes[-2]
                    
                    # Previous: close <= EMA10, Current: close > EMA10
                    close_above_ema10 = (
                        prev_close <= ema10_prev and
                        latest_monthly.close > ema10_current
                    )
            
            crossover_condition = crossover_detected or close_above_ema10
            
            reason_parts = []
            if crossover_detected:
                reason_parts.append("EMA10 crossed above EMA20")
            if close_above_ema10:
                reason_parts.append("Close crossed above EMA10")
            
            reason = " OR ".join(reason_parts) if reason_parts else "No crossover detected"
            
            conditions.append(StrategyCondition(
                name="ema_crossover",
                description="EMA10 cross above EMA20 OR Close cross above EMA10",
                passed=crossover_condition,
                expected_value="At least one crossover",
                actual_value="Crossover detected" if crossover_condition else "No crossover",
                reason=reason,
                weight=2.5,
            ))
            
            # Calculate overall pass/fail
            passed = all(c.passed for c in conditions)
            
            # Calculate rank score
            rank_score = self.calculate_rank_score(conditions)
            
            # Bonus for very strong monthly moves
            if passed and monthly_change_pct >= 30:
                rank_score += 10
            
            return StrategyResult(
                symbol=symbol,
                token=token,
                passed=passed,
                conditions=conditions,
                price=latest_monthly.close,
                volume=latest_monthly.volume,
                rank_score=rank_score,
                data_date=datetime.combine(latest_monthly.month_end_date, datetime.min.time()),
            )
            
        except Exception as e:
            logger.error(
                "Error evaluating Multi-bagger Technical strategy",
                symbol=symbol,
                error=str(e),
            )
            return StrategyResult(
                symbol=symbol,
                token=token,
                passed=False,
                conditions=[
                    StrategyCondition(
                        name="evaluation_error",
                        description="Strategy evaluation",
                        passed=False,
                        reason=f"Error: {str(e)}",
                    )
                ],
                price=0,
                volume=0,
            )

    def get_required_data(self) -> dict[str, Any]:
        """Get required data specifications."""
        return {
            "daily_candles": {"days": 50, "complete_only": True},
            "monthly_candles": {"months": 25, "complete_only": True},
            "fundamentals": False,
        }

    def get_schedule(self) -> dict[str, Any]:
        """Get strategy schedule configuration."""
        return {
            "frequency": "monthly",
            "time": settings.monthly_scan_time,
            "requires_data_ready": True,
            "requires_complete_candles": ["daily", "monthly"],
        }
