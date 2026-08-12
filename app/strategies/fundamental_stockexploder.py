"""Fundamental Stockexploder strategy implementation."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.fundamentals.provider_factory import get_fundamentals_provider
from app.models.candle import DailyCandle
from app.models.fundamental import FundamentalData
from app.strategies.base_strategy import (
    BaseStrategy,
    StrategyCondition,
    StrategyResult,
)

logger = get_logger(__name__)


class FundamentalStockexploderStrategy(BaseStrategy):
    """
    Fundamental Stockexploder Strategy.
    
    Conditions (month-end after fundamentals refresh):
    1. Latest quarter EPS > Previous quarter EPS × 1.25
    2. Latest quarter sales > Previous quarter sales × 1.25
    3. Latest quarter EPS > Same quarter last year EPS
    4. Market cap < ₹5000 crores
    5. 1-month average volume > 50,000
    6. Price > ₹20
    7. RSI > 40
    8. Price > DMA200
    9. DMA50 > DMA200
    10. 3-year EPS growth > 20%
    """

    def __init__(self):
        """Initialize Fundamental Stockexploder strategy."""
        super().__init__(
            strategy_name="FundamentalStockexploder",
            strategy_version="1.0",
            description="Fundamental Stockexploder - Identifies small-cap stocks with strong fundamental and technical momentum",
        )
        self.fundamentals_provider = get_fundamentals_provider()

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
            return 50.0
        
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [max(0, change) for change in changes]
        losses = [abs(min(0, change)) for change in changes]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi

    def calculate_sma(self, values: list[float], period: int) -> Optional[float]:
        """
        Calculate Simple Moving Average.
        
        Args:
            values: List of values
            period: SMA period
            
        Returns:
            SMA value or None
        """
        if len(values) < period:
            return None
        
        return sum(values[-period:]) / period

    async def get_previous_quarter_data(
        self,
        db: AsyncSession,
        token: str,
        current_year: int,
        current_quarter: int,
    ) -> Optional[FundamentalData]:
        """
        Get previous quarter fundamental data.
        
        Args:
            db: Database session
            token: Symbol token
            current_year: Current fiscal year
            current_quarter: Current fiscal quarter
            
        Returns:
            Previous quarter data or None
        """
        # Calculate previous quarter
        if current_quarter == 1:
            prev_year = current_year - 1
            prev_quarter = 4
        else:
            prev_year = current_year
            prev_quarter = current_quarter - 1
        
        result = await db.execute(
            select(FundamentalData).where(
                and_(
                    FundamentalData.token == token,
                    FundamentalData.period_type == "quarterly",
                    FundamentalData.fiscal_year == prev_year,
                    FundamentalData.fiscal_quarter == prev_quarter,
                )
            )
        )
        
        return result.scalar_one_or_none()

    async def get_same_quarter_last_year_data(
        self,
        db: AsyncSession,
        token: str,
        current_year: int,
        current_quarter: int,
    ) -> Optional[FundamentalData]:
        """
        Get same quarter last year fundamental data.
        
        Args:
            db: Database session
            token: Symbol token
            current_year: Current fiscal year
            current_quarter: Current fiscal quarter
            
        Returns:
            Same quarter last year data or None
        """
        result = await db.execute(
            select(FundamentalData).where(
                and_(
                    FundamentalData.token == token,
                    FundamentalData.period_type == "quarterly",
                    FundamentalData.fiscal_year == current_year - 1,
                    FundamentalData.fiscal_quarter == current_quarter,
                )
            )
        )
        
        return result.scalar_one_or_none()

    async def evaluate(
        self,
        db: AsyncSession,
        symbol: str,
        token: str,
    ) -> StrategyResult:
        """
        Evaluate Fundamental Stockexploder strategy for a symbol.
        
        Args:
            db: Database session
            symbol: Stock symbol
            token: Symbol token
            
        Returns:
            Strategy evaluation result
        """
        logger.debug("Evaluating Fundamental Stockexploder strategy", symbol=symbol)
        
        conditions = []
        
        try:
            # Get latest quarterly fundamental data
            latest_fundamental = await self.fundamentals_provider.fetch_latest_quarterly_data(
                db, symbol
            )
            
            if not latest_fundamental:
                logger.warning("No fundamental data available", symbol=symbol)
                return StrategyResult(
                    symbol=symbol,
                    token=token,
                    passed=False,
                    conditions=[
                        StrategyCondition(
                            name="fundamental_data_availability",
                            description="Fundamental data available",
                            passed=False,
                            reason="No fundamental data found",
                        )
                    ],
                    price=0,
                    volume=0,
                )
            
            # Fetch daily candles for technical conditions
            result = await db.execute(
                select(DailyCandle)
                .where(
                    and_(
                        DailyCandle.token == token,
                        DailyCandle.is_complete == True,
                    )
                )
                .order_by(DailyCandle.date.desc())
                .limit(220)
            )
            daily_candles = list(reversed(result.scalars().all()))
            
            if len(daily_candles) < 200:
                logger.warning(
                    "Insufficient daily candles",
                    symbol=symbol,
                    available=len(daily_candles),
                )
                return StrategyResult(
                    symbol=symbol,
                    token=token,
                    passed=False,
                    conditions=[
                        StrategyCondition(
                            name="technical_data_availability",
                            description="Sufficient technical data",
                            passed=False,
                            reason=f"Only {len(daily_candles)} candles, need 200+",
                        )
                    ],
                    price=daily_candles[-1].close if daily_candles else 0,
                    volume=daily_candles[-1].volume if daily_candles else 0,
                )
            
            latest_daily = daily_candles[-1]
            
            # Condition 1: Latest quarter EPS > Previous quarter EPS × 1.25
            prev_quarter = await self.get_previous_quarter_data(
                db,
                token,
                latest_fundamental.fiscal_year,
                latest_fundamental.fiscal_quarter,
            )
            
            if prev_quarter and prev_quarter.eps and latest_fundamental.eps:
                threshold = prev_quarter.eps * 1.25
                eps_qoq_growth = latest_fundamental.eps > threshold
                
                conditions.append(StrategyCondition(
                    name="eps_qoq_growth",
                    description="Latest Q EPS > Previous Q EPS × 1.25",
                    passed=eps_qoq_growth,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{latest_fundamental.eps:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=latest_fundamental.eps,
                    reason=f"QoQ EPS growth: {((latest_fundamental.eps/prev_quarter.eps - 1) * 100):.1f}%",
                    weight=3.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="eps_qoq_growth",
                    description="Latest Q EPS > Previous Q EPS × 1.25",
                    passed=False,
                    reason="Previous quarter EPS data not available",
                ))
            
            # Condition 2: Latest quarter sales > Previous quarter sales × 1.25
            if prev_quarter and prev_quarter.sales and latest_fundamental.sales:
                threshold = prev_quarter.sales * 1.25
                sales_qoq_growth = latest_fundamental.sales > threshold
                
                conditions.append(StrategyCondition(
                    name="sales_qoq_growth",
                    description="Latest Q Sales > Previous Q Sales × 1.25",
                    passed=sales_qoq_growth,
                    expected_value=f"> {threshold:.2f}",
                    actual_value=f"{latest_fundamental.sales:.2f}",
                    numeric_expected=threshold,
                    numeric_actual=latest_fundamental.sales,
                    reason=f"QoQ Sales growth: {((latest_fundamental.sales/prev_quarter.sales - 1) * 100):.1f}%",
                    weight=3.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="sales_qoq_growth",
                    description="Latest Q Sales > Previous Q Sales × 1.25",
                    passed=False,
                    reason="Previous quarter sales data not available",
                ))
            
            # Condition 3: Latest quarter EPS > Same quarter last year EPS
            same_q_last_year = await self.get_same_quarter_last_year_data(
                db,
                token,
                latest_fundamental.fiscal_year,
                latest_fundamental.fiscal_quarter,
            )
            
            if same_q_last_year and same_q_last_year.eps and latest_fundamental.eps:
                eps_yoy_growth = latest_fundamental.eps > same_q_last_year.eps
                
                conditions.append(StrategyCondition(
                    name="eps_yoy_growth",
                    description="Latest Q EPS > Same Q Last Year EPS",
                    passed=eps_yoy_growth,
                    expected_value=f"> {same_q_last_year.eps:.2f}",
                    actual_value=f"{latest_fundamental.eps:.2f}",
                    numeric_expected=same_q_last_year.eps,
                    numeric_actual=latest_fundamental.eps,
                    reason=f"YoY EPS growth: {((latest_fundamental.eps/same_q_last_year.eps - 1) * 100):.1f}%",
                    weight=2.5,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="eps_yoy_growth",
                    description="Latest Q EPS > Same Q Last Year EPS",
                    passed=False,
                    reason="Same quarter last year EPS data not available",
                ))
            
            # Condition 4: Market cap < ₹5000 crores
            market_cap_tuple = await self.fundamentals_provider.fetch_market_cap(db, symbol)
            
            if market_cap_tuple:
                market_cap, unit = market_cap_tuple
                
                # Convert to crores if needed
                if unit.lower() == "millions":
                    market_cap_crores = market_cap / 10
                else:
                    market_cap_crores = market_cap
                
                small_cap = market_cap_crores < 5000
                
                conditions.append(StrategyCondition(
                    name="market_cap",
                    description="Market Cap < ₹5000 crores",
                    passed=small_cap,
                    expected_value="< 5000 crores",
                    actual_value=f"{market_cap_crores:.2f} crores",
                    numeric_expected=5000,
                    numeric_actual=market_cap_crores,
                    reason=f"Market cap: ₹{market_cap_crores:.0f} crores",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="market_cap",
                    description="Market Cap < ₹5000 crores",
                    passed=False,
                    reason="Market cap data not available",
                ))
            
            # Condition 5: 1-month average volume > 50,000
            if len(daily_candles) >= 20:
                recent_volumes = [float(c.volume) for c in daily_candles[-20:]]
                avg_volume = sum(recent_volumes) / len(recent_volumes)
                volume_filter = avg_volume > 50000
                
                conditions.append(StrategyCondition(
                    name="avg_volume",
                    description="1-month avg volume > 50,000",
                    passed=volume_filter,
                    expected_value="> 50,000",
                    actual_value=f"{avg_volume:,.0f}",
                    numeric_expected=50000,
                    numeric_actual=avg_volume,
                    reason=f"Avg volume: {avg_volume:,.0f}",
                    weight=1.5,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="avg_volume",
                    description="1-month avg volume > 50,000",
                    passed=False,
                    reason="Insufficient data for volume calculation",
                ))
            
            # Condition 6: Price > ₹20
            min_price = 20.0
            price_filter = latest_daily.close > min_price
            
            conditions.append(StrategyCondition(
                name="min_price",
                description="Price > ₹20",
                passed=price_filter,
                expected_value=f"> {min_price}",
                actual_value=f"{latest_daily.close:.2f}",
                numeric_expected=min_price,
                numeric_actual=latest_daily.close,
                reason="Meets minimum price" if price_filter else "Below minimum price",
                weight=1.0,
            ))
            
            # Condition 7: RSI > 40
            closes = [c.close for c in daily_candles]
            rsi = self.calculate_rsi(closes, period=14)
            rsi_filter = rsi > 40
            
            conditions.append(StrategyCondition(
                name="rsi",
                description="RSI > 40",
                passed=rsi_filter,
                expected_value="> 40",
                actual_value=f"{rsi:.2f}",
                numeric_expected=40,
                numeric_actual=rsi,
                reason=f"RSI: {rsi:.2f}",
                weight=1.5,
            ))
            
            # Condition 8: Price > DMA200
            dma200 = self.calculate_sma(closes, 200)
            
            if dma200:
                above_dma200 = latest_daily.close > dma200
                
                conditions.append(StrategyCondition(
                    name="above_dma200",
                    description="Price > DMA200",
                    passed=above_dma200,
                    expected_value=f"> {dma200:.2f}",
                    actual_value=f"{latest_daily.close:.2f}",
                    numeric_expected=dma200,
                    numeric_actual=latest_daily.close,
                    reason="Above 200-day MA" if above_dma200 else "Below 200-day MA",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="above_dma200",
                    description="Price > DMA200",
                    passed=False,
                    reason="Insufficient data for DMA200",
                ))
            
            # Condition 9: DMA50 > DMA200
            dma50 = self.calculate_sma(closes, 50)
            
            if dma50 and dma200:
                ma_aligned = dma50 > dma200
                
                conditions.append(StrategyCondition(
                    name="ma_alignment",
                    description="DMA50 > DMA200",
                    passed=ma_aligned,
                    expected_value=f"> {dma200:.2f}",
                    actual_value=f"{dma50:.2f}",
                    numeric_expected=dma200,
                    numeric_actual=dma50,
                    reason="Bullish MA alignment" if ma_aligned else "MAs not aligned",
                    weight=2.0,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="ma_alignment",
                    description="DMA50 > DMA200",
                    passed=False,
                    reason="Insufficient data for MA calculation",
                ))
            
            # Condition 10: 3-year EPS growth > 20%
            eps_growth_3y = await self.fundamentals_provider.calculate_eps_growth_3y(
                db, symbol
            )
            
            if eps_growth_3y is not None:
                growth_filter = eps_growth_3y > 20
                
                conditions.append(StrategyCondition(
                    name="eps_growth_3y",
                    description="3-year EPS growth > 20%",
                    passed=growth_filter,
                    expected_value="> 20%",
                    actual_value=f"{eps_growth_3y:.2f}%",
                    numeric_expected=20,
                    numeric_actual=eps_growth_3y,
                    reason=f"3Y EPS CAGR: {eps_growth_3y:.2f}%",
                    weight=2.5,
                ))
            else:
                conditions.append(StrategyCondition(
                    name="eps_growth_3y",
                    description="3-year EPS growth > 20%",
                    passed=False,
                    reason="3-year EPS growth data not available",
                ))
            
            # Calculate overall pass/fail
            passed = all(c.passed for c in conditions)
            
            # Calculate rank score
            rank_score = self.calculate_rank_score(conditions)
            
            # Bonus for exceptional growth
            if passed and latest_fundamental.eps and prev_quarter and prev_quarter.eps:
                qoq_growth = (latest_fundamental.eps / prev_quarter.eps - 1) * 100
                if qoq_growth > 50:  # >50% QoQ growth
                    rank_score += 15
            
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
                "Error evaluating Fundamental Stockexploder strategy",
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
            "daily_candles": {"days": 220, "complete_only": True},
            "fundamentals": True,
            "quarterly_data": {"quarters": 8},
        }

    def get_schedule(self) -> dict[str, Any]:
        """Get strategy schedule configuration."""
        return {
            "frequency": "monthly",
            "time": settings.monthly_scan_time,
            "requires_data_ready": True,
            "requires_complete_candles": ["daily"],
            "requires_fundamentals_refresh": True,
        }
