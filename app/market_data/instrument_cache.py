"""Instrument master cache management."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_context
from app.core.logging import get_logger
from app.market_data.angel_one_client import AngelOneClient
from app.models.instrument import Instrument

logger = get_logger(__name__)


class InstrumentCache:
    """Manage instrument master data with caching."""

    def __init__(self):
        """Initialize instrument cache."""
        self._last_refresh: Optional[datetime] = None
        self._cache_ttl = timedelta(hours=settings.instrument_cache_ttl_hours)
        logger.info("Instrument cache initialized", ttl_hours=settings.instrument_cache_ttl_hours)

    async def is_cache_valid(self) -> bool:
        """
        Check if instrument cache is valid.
        
        Returns:
            True if cache is valid, False if refresh needed
        """
        if not self._last_refresh:
            return False
        
        age = datetime.utcnow() - self._last_refresh
        is_valid = age < self._cache_ttl
        
        logger.debug(
            "Cache validity check",
            is_valid=is_valid,
            age_seconds=age.total_seconds(),
            ttl_seconds=self._cache_ttl.total_seconds(),
        )
        
        return is_valid

    async def get_instrument_count(self, db: AsyncSession) -> int:
        """
        Get count of instruments in cache.
        
        Args:
            db: Database session
            
        Returns:
            Number of instruments
        """
        result = await db.execute(
            select(Instrument).where(Instrument.is_active == True)
        )
        instruments = result.scalars().all()
        return len(instruments)

    async def refresh_from_angel_one(self) -> int:
        """
        Refresh instrument master from Angel One API.
        
        Returns:
            Number of instruments updated
            
        Raises:
            Exception: If refresh fails
        """
        logger.info("Starting instrument master refresh from Angel One")
        
        async with AngelOneClient() as client:
            # Angel One doesn't have a direct instrument master endpoint
            # We'll need to use search or maintain a static list
            # For now, we'll implement a basic NSE equity list
            
            # This is a placeholder - in production, you would:
            # 1. Download instrument master CSV from Angel One
            # 2. Parse and store in database
            # 3. Or maintain a curated list of NSE stocks
            
            logger.warning(
                "Angel One instrument master refresh not fully implemented",
                reason="Angel One API doesn't provide direct instrument master endpoint"
            )
            
            # For now, return 0 and log warning
            return 0

    async def refresh_instruments(self, force: bool = False) -> int:
        """
        Refresh instrument cache if needed.
        
        Args:
            force: Force refresh even if cache is valid
            
        Returns:
            Number of instruments updated
        """
        if not force and await self.is_cache_valid():
            logger.debug("Instrument cache is valid, skipping refresh")
            return 0
        
        logger.info("Refreshing instrument cache", force=force)
        
        try:
            count = await self.refresh_from_angel_one()
            self._last_refresh = datetime.utcnow()
            
            logger.info(
                "Instrument cache refreshed",
                instruments_updated=count,
                next_refresh=self._last_refresh + self._cache_ttl,
            )
            
            return count
            
        except Exception as e:
            logger.error("Instrument cache refresh failed", error=str(e))
            raise

    async def get_instrument_by_symbol(
        self,
        db: AsyncSession,
        symbol: str,
        exchange: str = "NSE",
    ) -> Optional[Instrument]:
        """
        Get instrument by symbol.
        
        Args:
            db: Database session
            symbol: Trading symbol
            exchange: Exchange (default: NSE)
            
        Returns:
            Instrument if found, None otherwise
        """
        result = await db.execute(
            select(Instrument)
            .where(
                Instrument.symbol == symbol,
                Instrument.exchange == exchange,
                Instrument.is_active == True,
            )
        )
        instrument = result.scalar_one_or_none()
        
        if instrument:
            logger.debug("Instrument found", symbol=symbol, token=instrument.token)
        else:
            logger.debug("Instrument not found", symbol=symbol, exchange=exchange)
        
        return instrument

    async def get_instrument_by_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> Optional[Instrument]:
        """
        Get instrument by token.
        
        Args:
            db: Database session
            token: Symbol token
            
        Returns:
            Instrument if found, None otherwise
        """
        result = await db.execute(
            select(Instrument)
            .where(
                Instrument.token == token,
                Instrument.is_active == True,
            )
        )
        instrument = result.scalar_one_or_none()
        
        if instrument:
            logger.debug("Instrument found", token=token, symbol=instrument.symbol)
        else:
            logger.debug("Instrument not found", token=token)
        
        return instrument

    async def get_all_active_instruments(
        self,
        db: AsyncSession,
        exchange: str = "NSE",
        instrument_type: Optional[str] = None,
    ) -> list[Instrument]:
        """
        Get all active instruments.
        
        Args:
            db: Database session
            exchange: Exchange filter (default: NSE)
            instrument_type: Instrument type filter (optional)
            
        Returns:
            List of active instruments
        """
        query = select(Instrument).where(
            Instrument.is_active == True,
            Instrument.exchange == exchange,
        )
        
        if instrument_type:
            query = query.where(Instrument.instrument_type == instrument_type)
        
        result = await db.execute(query)
        instruments = result.scalars().all()
        
        logger.debug(
            "Retrieved active instruments",
            count=len(instruments),
            exchange=exchange,
            instrument_type=instrument_type,
        )
        
        return list(instruments)

    async def add_or_update_instrument(
        self,
        db: AsyncSession,
        token: str,
        symbol: str,
        name: str,
        exchange: str = "NSE",
        instrument_type: str = "EQ",
        **kwargs
    ) -> Instrument:
        """
        Add or update instrument in cache.
        
        Args:
            db: Database session
            token: Symbol token
            symbol: Trading symbol
            name: Instrument name
            exchange: Exchange
            instrument_type: Instrument type
            **kwargs: Additional instrument attributes
            
        Returns:
            Created or updated instrument
        """
        # Check if instrument exists
        result = await db.execute(
            select(Instrument).where(Instrument.token == token)
        )
        instrument = result.scalar_one_or_none()
        
        if instrument:
            # Update existing
            instrument.symbol = symbol
            instrument.name = name
            instrument.exchange = exchange
            instrument.instrument_type = instrument_type
            instrument.is_active = kwargs.get("is_active", True)
            instrument.lot_size = kwargs.get("lot_size", 1)
            instrument.tick_size = kwargs.get("tick_size", 0.05)
            instrument.isin = kwargs.get("isin")
            instrument.raw_data = kwargs.get("raw_data")
            instrument.updated_at = datetime.utcnow()
            
            logger.debug("Instrument updated", symbol=symbol, token=token)
        else:
            # Create new
            instrument = Instrument(
                token=token,
                symbol=symbol,
                name=name,
                exchange=exchange,
                instrument_type=instrument_type,
                is_active=kwargs.get("is_active", True),
                lot_size=kwargs.get("lot_size", 1),
                tick_size=kwargs.get("tick_size", 0.05),
                isin=kwargs.get("isin"),
                raw_data=kwargs.get("raw_data"),
            )
            db.add(instrument)
            
            logger.debug("Instrument created", symbol=symbol, token=token)
        
        await db.flush()
        return instrument

    async def deactivate_instrument(
        self,
        db: AsyncSession,
        token: str,
    ) -> bool:
        """
        Deactivate an instrument.
        
        Args:
            db: Database session
            token: Symbol token
            
        Returns:
            True if deactivated, False if not found
        """
        result = await db.execute(
            select(Instrument).where(Instrument.token == token)
        )
        instrument = result.scalar_one_or_none()
        
        if instrument:
            instrument.is_active = False
            instrument.updated_at = datetime.utcnow()
            await db.flush()
            
            logger.info("Instrument deactivated", symbol=instrument.symbol, token=token)
            return True
        
        logger.warning("Instrument not found for deactivation", token=token)
        return False

    async def get_cache_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Cache statistics
        """
        async with get_db_context() as db:
            total_count = await self.get_instrument_count(db)
        
        is_valid = await self.is_cache_valid()
        
        stats = {
            "total_instruments": total_count,
            "is_valid": is_valid,
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "cache_ttl_seconds": self._cache_ttl.total_seconds(),
        }
        
        if self._last_refresh:
            age = datetime.utcnow() - self._last_refresh
            stats["age_seconds"] = age.total_seconds()
            stats["next_refresh"] = (self._last_refresh + self._cache_ttl).isoformat()
        
        return stats
