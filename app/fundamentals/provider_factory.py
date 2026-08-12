"""Factory for creating fundamentals provider instances."""

from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.fundamentals.base_provider import BaseFundamentalsProvider
from app.fundamentals.mock_provider import MockFundamentalsProvider

logger = get_logger(__name__)

_provider_instance: Optional[BaseFundamentalsProvider] = None


def get_fundamentals_provider() -> BaseFundamentalsProvider:
    """
    Get fundamentals provider instance (singleton).
    
    Returns:
        Configured fundamentals provider
        
    Raises:
        ValueError: If provider type is not supported
    """
    global _provider_instance
    
    if _provider_instance is not None:
        return _provider_instance
    
    provider_type = settings.fundamentals_provider.lower()
    
    logger.info("Creating fundamentals provider", provider_type=provider_type)
    
    if provider_type == "mock":
        _provider_instance = MockFundamentalsProvider()
    elif provider_type == "angel_one":
        # Angel One provider would be implemented here
        # For now, fall back to mock with warning
        logger.warning(
            "Angel One fundamentals provider not fully implemented, using mock",
            reason="Angel One API has limited fundamental data support"
        )
        _provider_instance = MockFundamentalsProvider()
    else:
        raise ValueError(
            f"Unsupported fundamentals provider: {provider_type}. "
            f"Supported providers: 'mock', 'angel_one'"
        )
    
    logger.info(
        "Fundamentals provider created",
        provider=_provider_instance.provider_name,
    )
    
    return _provider_instance


def reset_provider() -> None:
    """Reset provider instance (useful for testing)."""
    global _provider_instance
    _provider_instance = None
    logger.debug("Fundamentals provider instance reset")
