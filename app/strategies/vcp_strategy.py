"""VCP (Volatility Contraction Pattern) strategy implementation."""

from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.candle import DailyCandle, WeeklyCandle
from app.strategies.base_strategy import (
    BaseStrategy,
    StrategyCondition,
    StrategyResult,
)

logger = get_logger(__name__)


class VCPStrategy(BaseStrategy):
    """
    VCP (Volatility Contraction Pattern) Strategy.
    
    Conditions:
    1. ATR(14)[today] < ATR(14)[10 days ago]
    2. ATR(14)[today] / close[today] < 0.08
    3. close[today] > 0.75 × max(weekly close over last 52 completed weeks)
    4. EMA50 > EMA150 > EMA200
    5. close > EMA50
    6. close > ₹10
    7. close × volume > ₹1,000,000
    """

    def __init__(self):
        """Initialize VCP strategy."""
        super().__init__(
            strategy_name="VCP",
            strategy_version="1.0",
            description="Volatility Contraction Pattern - identifies stocks with contracting volatility near 52-week highs",
        )

    def calculate_atr(self, candles: list[DailyCandle], period: int = 14) -> list[float]:
        """
        Calculate Average True Range.
        
        Args:
            candles: List of daily candles (sorted by date ascending)
            period: ATR period
            
        Returns:
            List of ATR values
        """
        if len(candles) < period + 1:
            return []
        
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i-1].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        # Calculate ATR using EMA
        atr_values = []
        if len(true_ranges) >= period:
            # Initial ATR is simple average
            initial_atr = sum(true_ranges[:period]) / period
            atr_values.append(initial_atr)
            
            # Subsequent ATRs use EMA formula
            multiplier = 1 / period
            for tr in true_ranges[period:]:
                new_atr = (tr * multiplier) + (atr_values[-1] * (1 - multiplier))
                atr_values.append(new_atr)
        
        return atr_values

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

    async def evaluate(
        self,
        db: AsyncSession,
        symbol: str,
        token: str,
    ) -> StrategyResult:
        """
        Evaluate VCP strategy for a symbol.
        
        Args:
            db: Database session
            symbol: Stock symbol
            token: Symbol token
            
        Returns:
            Strategy evaluation result
        """
        logger.debug("Evaluating VCP strategy", symbol=symbol)
        
        conditions = []
        
        try:
            # Fetch daily candles (need 200+ for EMA200)
            result = await db.execute(
                select(DailyCandle)
                .where(
                    and_(
                        DailyCandle.token == token,
                        DailyCandle.is_complete == True,
                    )
                )
                .order_by(DailyCandle.date.desc())
                .limit(250)
            )
            daily_candles = list(reversed(result.scalars().all()))
            
            if len(daily_candles) < 200:
                logger.warning(
                    "Insufficient daily candles for VCP",
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
                            reason=f"Only {len(daily_candles)} candles available, need 200+",
                        )
                    ],
                    price=daily_candles[-1].close if daily_candles else 0,
                    volume=daily_candles[-1].volume if daily_candles else 0,
                )
            
            # Get latest candle
            latest = daily_candles[-1]
            
            # Fetch weekly candles (need 52 completed weeks)
            result = await db.execute(
                select(WeeklyCandle)
                .where(
                    and_(
                        WeeklyCandle.token == token,
                        WeeklyCandle.is_complete == True,
                    )
                )
                .order_by(WeeklyCandle.week_start_date.desc())
                .limit(52)
            )
            weekly_candles = result.scalars().all()
            
            # Condition 1: ATR(14)[today] < ATR(14)[10 days ago]
            atr_values = self.calculate_atr(daily_candles, period=14)
            if len(atr_values) >= 11:
                atr_today = atr_values[-1]
                atr_10_days_ago = atr_values[-11]
                atr_contracting = atr_today < atr_10_days_ago
                
                conditions.append(StrategyCondition(
                    name="atr_contracting",
                    description="ATR(14) today < ATR(14) 10 days ago",
                    passed=atr_contracting,
                    expected_value=f"< {atr_10_days_ago:.2f}",
                    actual_value=f"{atr_today:.2f}",
                    numeric_expected=atr_10_days_ago,
                    numeric_actual=atr_today,
                    reason="Volatility is contracting" if atr_contracting else "Volatility not contracting",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="atr_contracting",
                    description="ATR(14) today < ATR(14) 10 days ago",
                    passed=False,
                    reason="Insufficient data for ATR calculation",
                ))
            
            # Condition 2: ATR(14)[today] / close[today] < 0.08
            if len(atr_values) >= 1:
                atr_today = atr_values[-1]
                atr_ratio = atr_today / latest.close
                low_volatility = atr_ratio < 0.08
                
                conditions.append(StrategyCondition(
                    name="low_volatility",
                    description="ATR(14) / close < 0.08",
                    passed=low_volatility,
                    expected_value="< 0.08",
                    actual_value=f"{atr_ratio:.4f}",
                    numeric_expected=0.08,
                    numeric_actual=atr_ratio,
                    reason="Low relative volatility" if low_volatility else "Volatility too high",
                    weight=2.0,
                ))
            
            # Condition 3: close > 0.75 × max(weekly close over last 52 weeks)
            if len(weekly_candles) >= 52:
                max_weekly_close = max(w.close for w in weekly_candles)
                threshold = 0.75 * max_weekly_close
                near_52w_high = latest.close > threshold
                
                conditions.append(StrategyCondition(
                    name="near_52w_high",
                    description="Close > 75% of 52-week high",
                    passed=near_52w_high,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{latest.close:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=latest.close,
                    reason=f"Price at {(latest.close/max_weekly_close)*100:.1f}% of 52W high",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="near_52w_high",
                    description="Close > 75% of 52-week high",
                    passed=False,
                    reason=f"Only {len(weekly_candles)} weeks available, need 52",
                ))
            
            # Condition 4 & 5: EMA alignment and close > EMA50
            closes = [c.close for c in daily_candles]
            ema50 = self.calculate_ema(closes, 50)
            ema150 = self.calculate_ema(closes, 150)
            ema200 = self.calculate_ema(closes, 200)
            
            if ema50 and ema150 and ema200:
                ema50_val = ema50[-1]
                ema150_val = ema150[-1]
                ema200_val = ema200[-1]
                
                ema_aligned = ema50_val > ema150_val > ema200_val
                conditions.append(StrategyCondition(
                    name="ema_alignment",
                    description="EMA50 > EMA150 > EMA200",
                    passed=ema_aligned,
                    expected_value="EMA50 > EMA150 > EMA200",
                    actual_value=f"{ema50_val:.2f} > {ema150_val:.2f} > {ema200_val:.2f}",
                    reason="Bullish EMA alignment" if ema_aligned else "EMAs not aligned",
                    weight=2.0,
                ))
                
                above_ema50 = latest.close > ema50_val
                conditions.append(StrategyCondition(
                    name="above_ema50",
                    description="Close > EMA50",
                    passed=above_ema50,
                    expected_value=f"> {ema50_val:.2f}",
                    actual_value=f"{latest.close:.2f}",
                    numeric_expected=ema50_val,
                    numeric_actual=latest.close,
                    reason="Above EMA50" if above_ema50 else "Below EMA50",
                    weight=1.5,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="ema_alignment",
                    description="EMA50 > EMA150 > EMA200",
                    passed=False,
                    reason="Insufficient data for EMA calculation",
                ))
                conditions.append(StrategyCondition(
                    name="above_ema50",
                    description="Close > EMA50",
                    passed=False,
                    reason="Insufficient data for EMA calculation",
                ))
            
            # Condition 6: close > ₹10
            min_price = settings.min_price
            price_filter = latest.close > min_price
            conditions.append(StrategyCondition(
                name="min_price",
                description=f"Close > ₹{min_price}",
                passed=price_filter,
                expected_value=f"> {min_price}",
                actual_value=f"{latest.close:.2f}",
                numeric_expected=min_price,
                numeric_actual=latest.close,
                reason="Meets minimum price" if price_filter else "Below minimum price",
                weight=1.0,
            ))
            
            # Condition 7: close × volume > ₹1,000,000
            turnover = latest.close * latest.volume
            min_turnover = 1_000_000
            turnover_filter = turnover > min_turnover
            conditions.append(StrategyCondition(
                name="min_turnover",
                description="Close × Volume > ₹1,000,000",
                passed=turnover_filter,
                expected_value=f"> {min_turnover:,}",
                actual_value=f"{turnover:,.0f}",
                numeric_expected=min_turnover,
                numeric_actual=turnover,
                reason=f"Turnover: ₹{turnover:,.0f}",
                weight=1.5,
            ))
            
            # Calculate overall pass/fail
            passed = all(c.passed for c in conditions)
            
            # Calculate rank score
            rank_score = self.calculate_rank_score(conditions)
            
            # Bonus for strong signals
            if passed and len(atr_values) >= 11:
                atr_ratio = atr_values[-1] / latest.close
                if atr_ratio < 0.05:  # Very low volatility
                    rank_score += 5
            
            return StrategyResult(
                symbol=symbol,
                token=token,
                passed=passed,
                conditions=conditions,
                price=latest.close,
                volume=latest.volume,
                rank_score=rank_score,
                data_date=datetime.combine(latest.date, datetime.min.time()),
            )
            
        except Exception as e:
            logger.error(
                "Error evaluating VCP strategy",
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
            "daily_candles": {"days": 250, "complete_only": True},
            "weekly_candles": {"weeks": 52, "complete_only": True},
            "fundamentals": False,
        }

    def get_schedule(self) -> dict[str, Any]:
        """Get strategy schedule configuration."""
        return {
            "frequency": "daily",
            "time": settings.vcp_scan_time,
            "requires_data_ready": True,
            "requires_complete_candles": ["daily"],
        }
