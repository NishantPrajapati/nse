"""Candle data management with incremental ingestion and derived timeframes."""

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.market_data.angel_one_client import AngelOneClient
from app.models.candle import DailyCandle, MonthlyCandle, WeeklyCandle
from app.models.instrument import Instrument

logger = get_logger(__name__)


class CandleManager:
    """Manage candle data ingestion and derived timeframes."""

    def __init__(self):
        """Initialize candle manager."""
        logger.info("Candle manager initialized")

    async def get_latest_daily_candle_date(
        self,
        db: AsyncSession,
        token: str,
    ) -> Optional[date]:
        """
        Get the latest daily candle date for a token.
        
        Args:
            db: Database session
            token: Symbol token
            
        Returns:
            Latest candle date or None
        """
        result = await db.execute(
            select(DailyCandle.date)
            .where(DailyCandle.token == token)
            .order_by(DailyCandle.date.desc())
            .limit(1)
        )
        latest_date = result.scalar_one_or_none()
        
        if latest_date:
            logger.debug("Latest daily candle found", token=token, date=latest_date)
        else:
            logger.debug("No daily candles found", token=token)
        
        return latest_date

    async def ingest_daily_candles(
        self,
        db: AsyncSession,
        instrument: Instrument,
        from_date: date,
        to_date: date,
        client: AngelOneClient,
    ) -> int:
        """
        Ingest daily candles for an instrument.
        
        Args:
            db: Database session
            instrument: Instrument to fetch data for
            from_date: Start date
            to_date: End date
            client: Angel One client
            
        Returns:
            Number of candles ingested
        """
        logger.info(
            "Ingesting daily candles",
            symbol=instrument.symbol,
            token=instrument.token,
            from_date=from_date,
            to_date=to_date,
        )
        
        try:
            # Format dates for Angel One API
            from_str = from_date.strftime("%Y-%m-%d 09:15")
            to_str = to_date.strftime("%Y-%m-%d 15:30")
            
            # Fetch candle data
            response = await client.get_candle_data(
                exchange=instrument.exchange,
                symbol_token=instrument.token,
                interval="ONE_DAY",
                from_date=from_str,
                to_date=to_str,
            )
            
            if not response.get("status"):
                error_msg = response.get("message", "Unknown error")
                logger.error(
                    "Failed to fetch candle data",
                    symbol=instrument.symbol,
                    error=error_msg,
                )
                return 0
            
            candles_data = response.get("data", [])
            if not candles_data:
                logger.warning("No candle data returned", symbol=instrument.symbol)
                return 0
            
            # Process and store candles
            count = 0
            for candle in candles_data:
                # Angel One candle format: [timestamp, open, high, low, close, volume]
                if len(candle) < 6:
                    logger.warning("Invalid candle data format", candle=candle)
                    continue
                
                candle_date = datetime.fromisoformat(candle[0]).date()
                
                # Check if candle already exists
                result = await db.execute(
                    select(DailyCandle).where(
                        and_(
                            DailyCandle.token == instrument.token,
                            DailyCandle.date == candle_date,
                        )
                    )
                )
                existing = result.scalar_one_or_none()
                
                open_price = float(candle[1])
                high_price = float(candle[2])
                low_price = float(candle[3])
                close_price = float(candle[4])
                volume = int(candle[5])
                
                # Calculate change
                change = close_price - open_price
                change_percent = (change / open_price * 100) if open_price > 0 else 0
                
                # Determine if candle is complete (not today)
                is_complete = candle_date < date.today()
                
                if existing:
                    # Update existing candle
                    existing.open = open_price
                    existing.high = high_price
                    existing.low = low_price
                    existing.close = close_price
                    existing.volume = volume
                    existing.change = change
                    existing.change_percent = change_percent
                    existing.is_complete = is_complete
                    existing.source_timestamp = datetime.fromisoformat(candle[0])
                    existing.received_timestamp = datetime.utcnow()
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new candle
                    daily_candle = DailyCandle(
                        instrument_id=instrument.id,
                        token=instrument.token,
                        symbol=instrument.symbol,
                        date=candle_date,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=volume,
                        change=change,
                        change_percent=change_percent,
                        is_complete=is_complete,
                        source_timestamp=datetime.fromisoformat(candle[0]),
                        received_timestamp=datetime.utcnow(),
                    )
                    db.add(daily_candle)
                
                count += 1
            
            await db.flush()
            
            logger.info(
                "Daily candles ingested",
                symbol=instrument.symbol,
                count=count,
            )
            
            return count
            
        except Exception as e:
            logger.error(
                "Error ingesting daily candles",
                symbol=instrument.symbol,
                error=str(e),
            )
            raise

    async def derive_weekly_candles(
        self,
        db: AsyncSession,
        token: str,
        from_date: Optional[date] = None,
    ) -> int:
        """
        Derive weekly candles from daily candles.
        
        Args:
            db: Database session
            token: Symbol token
            from_date: Start date (optional, derives all if None)
            
        Returns:
            Number of weekly candles created/updated
        """
        logger.info("Deriving weekly candles", token=token, from_date=from_date)
        
        # Fetch daily candles
        query = select(DailyCandle).where(DailyCandle.token == token)
        if from_date:
            query = query.where(DailyCandle.date >= from_date)
        query = query.order_by(DailyCandle.date)
        
        result = await db.execute(query)
        daily_candles = result.scalars().all()
        
        if not daily_candles:
            logger.warning("No daily candles found for weekly derivation", token=token)
            return 0
        
        # Convert to DataFrame for easier processing
        df = pd.DataFrame([
            {
                "date": c.date,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "is_complete": c.is_complete,
            }
            for c in daily_candles
        ])
        
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        
        # Resample to weekly (Monday-based)
        weekly = df.resample("W-MON").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "is_complete": "all",  # All daily candles must be complete
        })
        
        count = 0
        instrument_id = daily_candles[0].instrument_id
        symbol = daily_candles[0].symbol
        
        for week_end, row in weekly.iterrows():
            if pd.isna(row["open"]):
                continue
            
            week_start = week_end - timedelta(days=6)
            year, week, _ = week_end.isocalendar()
            
            # Count trading days in this week
            trading_days = len(df[week_start:week_end])
            
            # Check if weekly candle exists
            result = await db.execute(
                select(WeeklyCandle).where(
                    and_(
                        WeeklyCandle.token == token,
                        WeeklyCandle.year == year,
                        WeeklyCandle.week == week,
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            change = row["close"] - row["open"]
            change_percent = (change / row["open"] * 100) if row["open"] > 0 else 0
            
            if existing:
                existing.open = float(row["open"])
                existing.high = float(row["high"])
                existing.low = float(row["low"])
                existing.close = float(row["close"])
                existing.volume = int(row["volume"])
                existing.change = change
                existing.change_percent = change_percent
                existing.is_complete = bool(row["is_complete"])
                existing.trading_days = trading_days
                existing.updated_at = datetime.utcnow()
            else:
                weekly_candle = WeeklyCandle(
                    instrument_id=instrument_id,
                    token=token,
                    symbol=symbol,
                    year=year,
                    week=week,
                    week_start_date=week_start.date(),
                    week_end_date=week_end.date(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    change=change,
                    change_percent=change_percent,
                    is_complete=bool(row["is_complete"]),
                    trading_days=trading_days,
                )
                db.add(weekly_candle)
            
            count += 1
        
        await db.flush()
        
        logger.info("Weekly candles derived", token=token, count=count)
        return count

    async def derive_monthly_candles(
        self,
        db: AsyncSession,
        token: str,
        from_date: Optional[date] = None,
    ) -> int:
        """
        Derive monthly candles from daily candles.
        
        Args:
            db: Database session
            token: Symbol token
            from_date: Start date (optional, derives all if None)
            
        Returns:
            Number of monthly candles created/updated
        """
        logger.info("Deriving monthly candles", token=token, from_date=from_date)
        
        # Fetch daily candles
        query = select(DailyCandle).where(DailyCandle.token == token)
        if from_date:
            query = query.where(DailyCandle.date >= from_date)
        query = query.order_by(DailyCandle.date)
        
        result = await db.execute(query)
        daily_candles = result.scalars().all()
        
        if not daily_candles:
            logger.warning("No daily candles found for monthly derivation", token=token)
            return 0
        
        # Convert to DataFrame
        df = pd.DataFrame([
            {
                "date": c.date,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "is_complete": c.is_complete,
            }
            for c in daily_candles
        ])
        
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        
        # Resample to monthly
        monthly = df.resample("M").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "is_complete": "all",
        })
        
        count = 0
        instrument_id = daily_candles[0].instrument_id
        symbol = daily_candles[0].symbol
        
        for month_end, row in monthly.iterrows():
            if pd.isna(row["open"]):
                continue
            
            year = month_end.year
            month = month_end.month
            month_start = month_end.replace(day=1)
            
            # Count trading days in this month
            trading_days = len(df[month_start:month_end])
            
            # Check if monthly candle exists
            result = await db.execute(
                select(MonthlyCandle).where(
                    and_(
                        MonthlyCandle.token == token,
                        MonthlyCandle.year == year,
                        MonthlyCandle.month == month,
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            change = row["close"] - row["open"]
            change_percent = (change / row["open"] * 100) if row["open"] > 0 else 0
            
            if existing:
                existing.open = float(row["open"])
                existing.high = float(row["high"])
                existing.low = float(row["low"])
                existing.close = float(row["close"])
                existing.volume = int(row["volume"])
                existing.change = change
                existing.change_percent = change_percent
                existing.is_complete = bool(row["is_complete"])
                existing.trading_days = trading_days
                existing.updated_at = datetime.utcnow()
            else:
                monthly_candle = MonthlyCandle(
                    instrument_id=instrument_id,
                    token=token,
                    symbol=symbol,
                    year=year,
                    month=month,
                    month_start_date=month_start.date(),
                    month_end_date=month_end.date(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    change=change,
                    change_percent=change_percent,
                    is_complete=bool(row["is_complete"]),
                    trading_days=trading_days,
                )
                db.add(monthly_candle)
            
            count += 1
        
        await db.flush()
        
        logger.info("Monthly candles derived", token=token, count=count)
        return count

    async def validate_data_ready(
        self,
        db: AsyncSession,
        check_date: date,
    ) -> dict:
        """
        Validate if data is ready for the given date.
        
        Args:
            db: Database session
            check_date: Date to validate
            
        Returns:
            Validation result with status and details
        """
        logger.info("Validating data readiness", check_date=check_date)
        
        # Check daily candles
        result = await db.execute(
            select(DailyCandle)
            .where(
                and_(
                    DailyCandle.date == check_date,
                    DailyCandle.is_complete == True,
                )
            )
        )
        daily_candles = result.scalars().all()
        
        # Check data delay
        max_delay_hours = settings.max_data_delay_hours
        now = datetime.utcnow()
        
        delayed_count = 0
        for candle in daily_candles:
            if candle.received_timestamp:
                delay = (now - candle.received_timestamp).total_seconds() / 3600
                if delay > max_delay_hours:
                    delayed_count += 1
        
        is_ready = len(daily_candles) > 0 and delayed_count == 0
        
        validation = {
            "is_ready": is_ready,
            "check_date": check_date.isoformat(),
            "daily_candles_count": len(daily_candles),
            "delayed_count": delayed_count,
            "max_delay_hours": max_delay_hours,
        }
        
        logger.info(
            "Data validation complete",
            is_ready=is_ready,
            candles=len(daily_candles),
            delayed=delayed_count,
        )
        
        return validation

    async def cleanup_old_candles(
        self,
        db: AsyncSession,
        days_to_keep: int = 730,  # 2 years
    ) -> dict:
        """
        Clean up old candle data.
        
        Args:
            db: Database session
            days_to_keep: Number of days to keep
            
        Returns:
            Cleanup statistics
        """
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        
        logger.info("Cleaning up old candles", cutoff_date=cutoff_date)
        
        # Delete old daily candles
        daily_result = await db.execute(
            delete(DailyCandle).where(DailyCandle.date < cutoff_date)
        )
        daily_deleted = daily_result.rowcount
        
        # Delete old weekly candles
        weekly_result = await db.execute(
            delete(WeeklyCandle).where(WeeklyCandle.week_start_date < cutoff_date)
        )
        weekly_deleted = weekly_result.rowcount
        
        # Delete old monthly candles
        monthly_result = await db.execute(
            delete(MonthlyCandle).where(MonthlyCandle.month_start_date < cutoff_date)
        )
        monthly_deleted = monthly_result.rowcount
        
        await db.flush()
        
        stats = {
            "cutoff_date": cutoff_date.isoformat(),
            "daily_deleted": daily_deleted,
            "weekly_deleted": weekly_deleted,
            "monthly_deleted": monthly_deleted,
            "total_deleted": daily_deleted + weekly_deleted + monthly_deleted,
        }
        
        logger.info("Cleanup complete", **stats)
        
        return stats
