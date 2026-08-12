"""Base provider interface for fundamentals data."""

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.fundamental import FundamentalData

logger = get_logger(__name__)


class BaseFundamentalsProvider(ABC):
    """Abstract base class for fundamentals data providers."""

    def __init__(self, provider_name: str):
        """
        Initialize provider.
        
        Args:
            provider_name: Name of the provider
        """
        self.provider_name = provider_name
        logger.info("Fundamentals provider initialized", provider=provider_name)

    @abstractmethod
    async def fetch_quarterly_data(
        self,
        db: AsyncSession,
        symbol: str,
        fiscal_year: int,
        fiscal_quarter: int,
    ) -> Optional[FundamentalData]:
        """
        Fetch quarterly fundamental data.
        
        Args:
            db: Database session
            symbol: Stock symbol
            fiscal_year: Fiscal year
            fiscal_quarter: Fiscal quarter (1-4)
            
        Returns:
            FundamentalData if available, None otherwise
        """
        pass

    @abstractmethod
    async def fetch_annual_data(
        self,
        db: AsyncSession,
        symbol: str,
        fiscal_year: int,
    ) -> Optional[FundamentalData]:
        """
        Fetch annual fundamental data.
        
        Args:
            db: Database session
            symbol: Stock symbol
            fiscal_year: Fiscal year
            
        Returns:
            FundamentalData if available, None otherwise
        """
        pass

    @abstractmethod
    async def fetch_latest_quarterly_data(
        self,
        db: AsyncSession,
        symbol: str,
    ) -> Optional[FundamentalData]:
        """
        Fetch latest quarterly fundamental data.
        
        Args:
            db: Database session
            symbol: Stock symbol
            
        Returns:
            Latest FundamentalData if available, None otherwise
        """
        pass

    @abstractmethod
    async def fetch_market_cap(
        self,
        db: AsyncSession,
        symbol: str,
    ) -> Optional[tuple[float, str]]:
        """
        Fetch current market capitalization.
        
        Args:
            db: Database session
            symbol: Stock symbol
            
        Returns:
            Tuple of (market_cap, unit) if available, None otherwise
            Unit is typically 'crores' or 'millions'
        """
        pass

    @abstractmethod
    async def calculate_eps_growth_3y(
        self,
        db: AsyncSession,
        symbol: str,
    ) -> Optional[float]:
        """
        Calculate 3-year EPS CAGR.
        
        Args:
            db: Database session
            symbol: Stock symbol
            
        Returns:
            3-year EPS growth percentage if calculable, None otherwise
        """
        pass

    @abstractmethod
    async def refresh_data(
        self,
        db: AsyncSession,
        symbol: str,
        force: bool = False,
    ) -> int:
        """
        Refresh fundamental data for a symbol.
        
        Args:
            db: Database session
            symbol: Stock symbol
            force: Force refresh even if data is recent
            
        Returns:
            Number of records updated/created
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if provider is accessible and functioning.
        
        Returns:
            True if healthy, False otherwise
        """
        pass

    async def get_provider_info(self) -> dict:
        """
        Get provider information.
        
        Returns:
            Provider metadata
        """
        return {
            "provider_name": self.provider_name,
            "capabilities": {
                "quarterly_data": True,
                "annual_data": True,
                "market_cap": True,
                "eps_growth": True,
            }
        }

    async def validate_data_quality(
        self,
        data: FundamentalData,
    ) -> tuple[bool, list[str]]:
        """
        Validate fundamental data quality.
        
        Args:
            data: Fundamental data to validate
            
        Returns:
            Tuple of (is_valid, list of issues)
        """
        issues = []
        
        # Check required fields
        if data.eps is None:
            issues.append("EPS is missing")
        
        if data.period_type == "quarterly":
            if data.fiscal_quarter is None:
                issues.append("Fiscal quarter is missing for quarterly data")
            if data.sales is None:
                issues.append("Sales data is missing")
        
        # Check data reasonableness
        if data.eps is not None and abs(data.eps) > 10000:
            issues.append(f"EPS value seems unreasonable: {data.eps}")
        
        if data.market_cap is not None and data.market_cap < 0:
            issues.append("Market cap cannot be negative")
        
        # Check date consistency
        if data.filing_date and data.period_end_date:
            if data.filing_date < data.period_end_date:
                issues.append("Filing date is before period end date")
        
        is_valid = len(issues) == 0
        
        if not is_valid:
            logger.warning(
                "Data quality issues found",
                symbol=data.symbol,
                issues=issues,
            )
        
        return is_valid, issues
