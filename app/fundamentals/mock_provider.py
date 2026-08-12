"""Mock fundamentals provider for testing and development."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.fundamentals.base_provider import BaseFundamentalsProvider
from app.models.fundamental import FundamentalData
from app.models.instrument import Instrument

logger = get_logger(__name__)


class MockFundamentalsProvider(BaseFundamentalsProvider):
    """Mock provider that generates synthetic fundamental data."""

    def __init__(self):
        """Initialize mock provider."""
        super().__init__("mock")
        logger.info("Mock fundamentals provider initialized")

    async def fetch_quarterly_data(
        self,
        db: AsyncSession,
        symbol: str,
        fiscal_year: int,
        fiscal_quarter: int,
    ) -> Optional[FundamentalData]:
        """
        Fetch or generate mock quarterly data.
        
        Args:
            db: Database session
            symbol: Stock symbol
            fiscal_year: Fiscal year
            fiscal_quarter: Fiscal quarter (1-4)
            
        Returns:
            Mock FundamentalData
        """
        logger.debug(
            "Fetching mock quarterly data",
            symbol=symbol,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
        )
        
        # Get instrument
        result = await db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            logger.warning("Instrument not found", symbol=symbol)
            return None
        
        # Check if data already exists
        result = await db.execute(
            select(FundamentalData).where(
                and_(
                    FundamentalData.token == instrument.token,
                    FundamentalData.period_type == "quarterly",
                    FundamentalData.fiscal_year == fiscal_year,
                    FundamentalData.fiscal_quarter == fiscal_quarter,
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing
        
        # Generate mock data
        # Use symbol hash for consistent but varied data
        symbol_hash = hash(symbol) % 1000
        
        # Calculate period end date
        quarter_end_months = {1: 3, 2: 6, 3: 9, 4: 12}
        period_end = date(fiscal_year, quarter_end_months[fiscal_quarter], 28)
        
        mock_data = FundamentalData(
            instrument_id=instrument.id,
            token=instrument.token,
            symbol=symbol,
            provider=self.provider_name,
            provider_id=f"MOCK-{symbol}-{fiscal_year}Q{fiscal_quarter}",
            period_type="quarterly",
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            period_end_date=period_end,
            filing_date=period_end,
            eps=10.0 + (symbol_hash % 50),
            eps_diluted=9.5 + (symbol_hash % 50),
            revenue=1000.0 + (symbol_hash % 5000),
            sales=1000.0 + (symbol_hash % 5000),
            net_income=100.0 + (symbol_hash % 500),
            operating_income=150.0 + (symbol_hash % 600),
            ebitda=200.0 + (symbol_hash % 700),
            market_cap=5000.0 + (symbol_hash % 10000),
            market_cap_unit="crores",
            shares_outstanding=100.0 + (symbol_hash % 200),
            eps_growth_yoy=15.0 + (symbol_hash % 30),
            eps_growth_qoq=5.0 + (symbol_hash % 15),
            revenue_growth_yoy=20.0 + (symbol_hash % 40),
            revenue_growth_qoq=8.0 + (symbol_hash % 20),
            pe_ratio=15.0 + (symbol_hash % 35),
            pb_ratio=2.0 + (symbol_hash % 8),
            is_restated=False,
            restatement_version=1,
            data_quality_score=0.85,
            source_timestamp=datetime.utcnow(),
        )
        
        db.add(mock_data)
        await db.flush()
        
        logger.info(
            "Mock quarterly data generated",
            symbol=symbol,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
        )
        
        return mock_data

    async def fetch_annual_data(
        self,
        db: AsyncSession,
        symbol: str,
        fiscal_year: int,
    ) -> Optional[FundamentalData]:
        """
        Fetch or generate mock annual data.
        
        Args:
            db: Database session
            symbol: Stock symbol
            fiscal_year: Fiscal year
            
        Returns:
            Mock FundamentalData
        """
        logger.debug(
            "Fetching mock annual data",
            symbol=symbol,
            fiscal_year=fiscal_year,
        )
        
        # Get instrument
        result = await db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            logger.warning("Instrument not found", symbol=symbol)
            return None
        
        # Check if data already exists
        result = await db.execute(
            select(FundamentalData).where(
                and_(
                    FundamentalData.token == instrument.token,
                    FundamentalData.period_type == "annual",
                    FundamentalData.fiscal_year == fiscal_year,
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing
        
        # Generate mock data
        symbol_hash = hash(symbol) % 1000
        period_end = date(fiscal_year, 3, 31)  # Assuming March year-end
        
        mock_data = FundamentalData(
            instrument_id=instrument.id,
            token=instrument.token,
            symbol=symbol,
            provider=self.provider_name,
            provider_id=f"MOCK-{symbol}-FY{fiscal_year}",
            period_type="annual",
            fiscal_year=fiscal_year,
            fiscal_quarter=None,
            period_end_date=period_end,
            filing_date=period_end,
            eps=40.0 + (symbol_hash % 200),
            eps_diluted=38.0 + (symbol_hash % 200),
            revenue=4000.0 + (symbol_hash % 20000),
            sales=4000.0 + (symbol_hash % 20000),
            net_income=400.0 + (symbol_hash % 2000),
            operating_income=600.0 + (symbol_hash % 2400),
            ebitda=800.0 + (symbol_hash % 2800),
            market_cap=5000.0 + (symbol_hash % 10000),
            market_cap_unit="crores",
            shares_outstanding=100.0 + (symbol_hash % 200),
            eps_growth_yoy=18.0 + (symbol_hash % 35),
            revenue_growth_yoy=22.0 + (symbol_hash % 45),
            eps_growth_3y=25.0 + (symbol_hash % 40),
            pe_ratio=15.0 + (symbol_hash % 35),
            pb_ratio=2.0 + (symbol_hash % 8),
            is_restated=False,
            restatement_version=1,
            data_quality_score=0.90,
            source_timestamp=datetime.utcnow(),
        )
        
        db.add(mock_data)
        await db.flush()
        
        logger.info(
            "Mock annual data generated",
            symbol=symbol,
            fiscal_year=fiscal_year,
        )
        
        return mock_data

    async def fetch_latest_quarterly_data(
        self,
        db: AsyncSession,
        symbol: str,
    ) -> Optional[FundamentalData]:
        """
        Fetch latest quarterly data.
        
        Args:
            db: Database session
            symbol: Stock symbol
            
        Returns:
            Latest quarterly FundamentalData
        """
        logger.debug("Fetching latest quarterly data", symbol=symbol)
        
        # Get instrument
        result = await db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            logger.warning("Instrument not found", symbol=symbol)
            return None
        
        # Get latest quarterly data
        result = await db.execute(
            select(FundamentalData)
            .where(
                and_(
                    FundamentalData.token == instrument.token,
                    FundamentalData.period_type == "quarterly",
                )
            )
            .order_by(
                FundamentalData.fiscal_year.desc(),
                FundamentalData.fiscal_quarter.desc(),
            )
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        
        if latest:
            return latest
        
        # Generate for current quarter if none exists
        current_year = datetime.now().year
        current_quarter = (datetime.now().month - 1) // 3 + 1
        
        return await self.fetch_quarterly_data(
            db, symbol, current_year, current_quarter
        )

    async def fetch_market_cap(
        self,
        db: AsyncSession,
        symbol: str,
    ) -> Optional[tuple[float, str]]:
        """
        Fetch mock market cap.
        
        Args:
            db: Database session
            symbol: Stock symbol
            
        Returns:
            Tuple of (market_cap, unit)
        """
        logger.debug("Fetching mock market cap", symbol=symbol)
        
        # Get latest data
        latest = await self.fetch_latest_quarterly_data(db, symbol)
        
        if latest and latest.market_cap:
            return (latest.market_cap, latest.market_cap_unit or "crores")
        
        # Generate mock market cap
        symbol_hash = hash(symbol) % 1000
        market_cap = 5000.0 + (symbol_hash % 10000)
        
        return (market_cap, "crores")

    async def calculate_eps_growth_3y(
        self,
        db: AsyncSession,
        symbol: str,
    ) -> Optional[float]:
        """
        Calculate mock 3-year EPS growth.
        
        Args:
            db: Database session
            symbol: Stock symbol
            
        Returns:
            3-year EPS growth percentage
        """
        logger.debug("Calculating mock 3Y EPS growth", symbol=symbol)
        
        # Get instrument
        result = await db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        instrument = result.scalar_one_or_none()
        
        if not instrument:
            return None
        
        # Check if we have stored 3Y growth
        result = await db.execute(
            select(FundamentalData)
            .where(
                and_(
                    FundamentalData.token == instrument.token,
                    FundamentalData.eps_growth_3y.isnot(None),
                )
            )
            .order_by(FundamentalData.fiscal_year.desc())
            .limit(1)
        )
        data = result.scalar_one_or_none()
        
        if data and data.eps_growth_3y:
            return data.eps_growth_3y
        
        # Generate mock 3Y growth
        symbol_hash = hash(symbol) % 1000
        growth_3y = 25.0 + (symbol_hash % 40)
        
        return growth_3y

    async def refresh_data(
        self,
        db: AsyncSession,
        symbol: str,
        force: bool = False,
    ) -> int:
        """
        Refresh mock data (no-op for mock provider).
        
        Args:
            db: Database session
            symbol: Stock symbol
            force: Force refresh
            
        Returns:
            Number of records updated (always 0 for mock)
        """
        logger.debug("Mock refresh requested", symbol=symbol, force=force)
        return 0

    async def health_check(self) -> bool:
        """
        Mock provider is always healthy.
        
        Returns:
            Always True
        """
        logger.debug("Mock provider health check")
        return True
