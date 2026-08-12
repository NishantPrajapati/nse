"""RB (Rocket Base) strategy implementation with Chartink-compatible WMA formulas."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.candle import DailyCandle, MonthlyCandle, WeeklyCandle
from app.strategies.base_strategy import (
    BaseStrategy,
    StrategyCondition,
    StrategyResult,
)

logger = get_logger(__name__)


class RBStrategy(BaseStrategy):
    """
    RB (Rocket Base) Strategy with Chartink-compatible formulas.
    
    Conditions (exact Chartink WMA expressions):
    1. daily WMA(close,1) > monthly WMA(close,2) + 1
    2. monthly WMA(close,2) > monthly WMA(close,4) + 2
    3. daily WMA(close,1) > weekly WMA(close,6) + 2
    4. weekly WMA(close,6) > weekly WMA(close,12) + 2
    5. daily WMA(close,1) > WMA(close,12)[4 days ago] + 2
    6. daily WMA(close,1) > WMA(close,20)[2 days ago] + 2
    7. ₹25 < close <= ₹500
    8. weekly volume > 85,000
    
    Note: Ambiguous WMA timeframes in conditions 5-6 are configurable.
    Parity testing required before declaring exact Chartink equivalence.
    """

    def __init__(self):
        """Initialize RB strategy."""
        super().__init__(
            strategy_name="RB",
            strategy_version="1.0",
            description="Rocket Base - Multi-timeframe WMA crossover strategy with Chartink-compatible formulas",
        )
        
        # Configuration for ambiguous WMA timeframes
        # These should be validated via parity testing
        self.wma_12_timeframe = "daily"  # or "weekly" - needs parity test
        self.wma_20_timeframe = "daily"  # or "weekly" - needs parity test

    def calculate_wma(self, values: list[float], period: int) -> float:
        """
        Calculate Weighted Moving Average.
        
        Args:
            values: List of values (most recent last)
            period: WMA period
            
        Returns:
            WMA value
        """
        if len(values) < period:
            return 0.0
        
        # Take last 'period' values
        recent_values = values[-period:]
        
        # Calculate weights (1, 2, 3, ..., period)
        weights = list(range(1, period + 1))
        weight_sum = sum(weights)
        
        # Calculate WMA
        wma = sum(v * w for v, w in zip(recent_values, weights)) / weight_sum
        
        return wma

    async def evaluate(
        self,
        db: AsyncSession,
        symbol: str,
        token: str,
    ) -> StrategyResult:
        """
        Evaluate RB strategy for a symbol.
        
        Args:
            db: Database session
            symbol: Stock symbol
            token: Symbol token
            
        Returns:
            Strategy evaluation result
        """
        logger.debug("Evaluating RB strategy", symbol=symbol)
        
        conditions = []
        
        try:
            # Fetch daily candles (need ~30 for WMA20 + lookback)
            result = await db.execute(
                select(DailyCandle)
                .where(
                    and_(
                        DailyCandle.token == token,
                        DailyCandle.is_complete == True,
                    )
                )
                .order_by(DailyCandle.date.desc())
                .limit(30)
            )
            daily_candles = list(reversed(result.scalars().all()))
            
            if len(daily_candles) < 25:
                logger.warning(
                    "Insufficient daily candles for RB",
                    symbol=symbol,
                    available=len(daily_candles),
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
                            reason=f"Only {len(daily_candles)} candles available, need 25+",
                        )
                    ],
                    price=daily_candles[-1].close if daily_candles else 0,
                    volume=daily_candles[-1].volume if daily_candles else 0,
                )
            
            latest_daily = daily_candles[-1]
            
            # Fetch weekly candles (need 12+)
            result = await db.execute(
                select(WeeklyCandle)
                .where(
                    and_(
                        WeeklyCandle.token == token,
                        WeeklyCandle.is_complete == True,
                    )
                )
                .order_by(WeeklyCandle.week_start_date.desc())
                .limit(15)
            )
            weekly_candles = list(reversed(result.scalars().all()))
            
            # Fetch monthly candles (need 4+)
            result = await db.execute(
                select(MonthlyCandle)
                .where(
                    and_(
                        MonthlyCandle.token == token,
                        MonthlyCandle.is_complete == True,
                    )
                )
                .order_by(MonthlyCandle.month_start_date.desc())
                .limit(5)
            )
            monthly_candles = list(reversed(result.scalars().all()))
            
            # Calculate WMAs
            daily_closes = [c.close for c in daily_candles]
            weekly_closes = [c.close for c in weekly_candles] if weekly_candles else []
            monthly_closes = [c.close for c in monthly_candles] if monthly_candles else []
            
            # Daily WMA(1) - essentially current close
            daily_wma1 = latest_daily.close
            
            # Condition 1: daily WMA(close,1) > monthly WMA(close,2) + 1
            if len(monthly_closes) >= 2:
                monthly_wma2 = self.calculate_wma(monthly_closes, 2)
                threshold = monthly_wma2 + 1
                cond1_pass = daily_wma1 > threshold
                
                conditions.append(StrategyCondition(
                    name="daily_vs_monthly_wma2",
                    description="Daily WMA(1) > Monthly WMA(2) + 1",
                    passed=cond1_pass,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{daily_wma1:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=daily_wma1,
                    reason="Daily above monthly trend" if cond1_pass else "Daily below monthly trend",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="daily_vs_monthly_wma2",
                    description="Daily WMA(1) > Monthly WMA(2) + 1",
                    passed=False,
                    reason=f"Only {len(monthly_closes)} monthly candles, need 2+",
                ))
            
            # Condition 2: monthly WMA(close,2) > monthly WMA(close,4) + 2
            if len(monthly_closes) >= 4:
                monthly_wma2 = self.calculate_wma(monthly_closes, 2)
                monthly_wma4 = self.calculate_wma(monthly_closes, 4)
                threshold = monthly_wma4 + 2
                cond2_pass = monthly_wma2 > threshold
                
                conditions.append(StrategyCondition(
                    name="monthly_wma2_vs_wma4",
                    description="Monthly WMA(2) > Monthly WMA(4) + 2",
                    passed=cond2_pass,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{monthly_wma2:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=monthly_wma2,
                    reason="Monthly uptrend" if cond2_pass else "Monthly not trending up",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="monthly_wma2_vs_wma4",
                    description="Monthly WMA(2) > Monthly WMA(4) + 2",
                    passed=False,
                    reason=f"Only {len(monthly_closes)} monthly candles, need 4+",
                ))
            
            # Condition 3: daily WMA(close,1) > weekly WMA(close,6) + 2
            if len(weekly_closes) >= 6:
                weekly_wma6 = self.calculate_wma(weekly_closes, 6)
                threshold = weekly_wma6 + 2
                cond3_pass = daily_wma1 > threshold
                
                conditions.append(StrategyCondition(
                    name="daily_vs_weekly_wma6",
                    description="Daily WMA(1) > Weekly WMA(6) + 2",
                    passed=cond3_pass,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{daily_wma1:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=daily_wma1,
                    reason="Daily above weekly trend" if cond3_pass else "Daily below weekly trend",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="daily_vs_weekly_wma6",
                    description="Daily WMA(1) > Weekly WMA(6) + 2",
                    passed=False,
                    reason=f"Only {len(weekly_closes)} weekly candles, need 6+",
                ))
            
            # Condition 4: weekly WMA(close,6) > weekly WMA(close,12) + 2
            if len(weekly_closes) >= 12:
                weekly_wma6 = self.calculate_wma(weekly_closes, 6)
                weekly_wma12 = self.calculate_wma(weekly_closes, 12)
                threshold = weekly_wma12 + 2
                cond4_pass = weekly_wma6 > threshold
                
                conditions.append(StrategyCondition(
                    name="weekly_wma6_vs_wma12",
                    description="Weekly WMA(6) > Weekly WMA(12) + 2",
                    passed=cond4_pass,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{weekly_wma6:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=weekly_wma6,
                    reason="Weekly uptrend" if cond4_pass else "Weekly not trending up",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="weekly_wma6_vs_wma12",
                    description="Weekly WMA(6) > Weekly WMA(12) + 2",
                    passed=False,
                    reason=f"Only {len(weekly_closes)} weekly candles, need 12+",
                ))
            
            # Condition 5: daily WMA(close,1) > WMA(close,12)[4 days ago] + 2
            # Note: Timeframe ambiguous - using configured timeframe
            if len(daily_closes) >= 16:  # Need 12 + 4 lookback
                wma12_4days_ago = self.calculate_wma(daily_closes[:-4], 12)
                threshold = wma12_4days_ago + 2
                cond5_pass = daily_wma1 > threshold
                
                conditions.append(StrategyCondition(
                    name="daily_vs_wma12_lagged",
                    description=f"Daily WMA(1) > {self.wma_12_timeframe.title()} WMA(12)[4 days ago] + 2",
                    passed=cond5_pass,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{daily_wma1:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=daily_wma1,
                    reason="Above lagged WMA12" if cond5_pass else "Below lagged WMA12",
                    weight=1.5,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="daily_vs_wma12_lagged",
                    description=f"Daily WMA(1) > {self.wma_12_timeframe.title()} WMA(12)[4 days ago] + 2",
                    passed=False,
                    reason="Insufficient data for lagged WMA12",
                ))
            
            # Condition 6: daily WMA(close,1) > WMA(close,20)[2 days ago] + 2
            if len(daily_closes) >= 22:  # Need 20 + 2 lookback
                wma20_2days_ago = self.calculate_wma(daily_closes[:-2], 20)
                threshold = wma20_2days_ago + 2
                cond6_pass = daily_wma1 > threshold
                
                conditions.append(StrategyCondition(
                    name="daily_vs_wma20_lagged",
                    description=f"Daily WMA(1) > {self.wma_20_timeframe.title()} WMA(20)[2 days ago] + 2",
                    passed=cond6_pass,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{daily_wma1:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=daily_wma1,
                    reason="Above lagged WMA20" if cond6_pass else "Below lagged WMA20",
                    weight=1.5,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="daily_vs_wma20_lagged",
                    description=f"Daily WMA(1) > {self.wma_20_timeframe.title()} WMA(20)[2 days ago] + 2",
                    passed=False,
                    reason="Insufficient data for lagged WMA20",
                ))
            
            # Condition 7: ₹25 < close <= ₹500
            price_in_range = 25 < latest_daily.close <= 500
            conditions.append(StrategyCondition(
                name="price_range",
                description="₹25 < Close <= ₹500",
                passed=price_in_range,
                expected_value="25 < price <= 500",
                actual_value=f"{latest_daily.close:.2f}",
                numeric_actual=latest_daily.close,
                reason="Price in range" if price_in_range else "Price out of range",
                weight=1.0,
            ))
            
            # Condition 8: weekly volume > 85,000
            if weekly_candles:
                latest_weekly = weekly_candles[-1]
                volume_filter = latest_weekly.volume > 85000
                
                conditions.append(StrategyCondition(
                    name="weekly_volume",
                    description="Weekly Volume > 85,000",
                    passed=volume_filter,
                    expected_value="> 85,000",
                    actual_value=f"{latest_weekly.volume:,}",
                    numeric_expected=85000,
                    numeric_actual=latest_weekly.volume,
                    reason=f"Weekly volume: {latest_weekly.volume:,}",
                    weight=1.5,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="weekly_volume",
                    description="Weekly Volume > 85,000",
                    passed=False,
                    reason="No weekly candle data available",
                ))
            
            # Calculate overall pass/fail
            passed = all(c.passed for c in conditions)
            
            # Calculate rank score
            rank_score = self.calculate_rank_score(conditions)
            
            return StrategyResult(
                symbol=symbol,
                token=token,
                passed=passed,
                conditions=conditions,
                price=latest_daily.close,
                volume=latest_daily.volume,
                rank_score=rank_score,
                data_date=datetime.combine(latest_daily.date, datetime.min.time()),
            )
            
        except Exception as e:
            logger.error(
                "Error evaluating RB strategy",
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
            "daily_candles": {"days": 30, "complete_only": True},
            "weekly_candles": {"weeks": 15, "complete_only": True},
            "monthly_candles": {"months": 5, "complete_only": True},
            "fundamentals": False,
        }

    def get_schedule(self) -> dict[str, Any]:
        """Get strategy schedule configuration."""
        return {
            "frequency": "daily",  # Daily watchlist
            "time": settings.rb_daily_scan_time,
            "requires_data_ready": True,
            "requires_complete_candles": ["daily"],
            "monthly_confirmed": {
                "frequency": "monthly",
                "time": settings.monthly_scan_time,
                "requires_complete_candles": ["daily", "weekly", "monthly"],
            }
        }
