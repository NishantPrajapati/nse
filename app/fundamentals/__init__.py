"""Fundamentals data module with provider abstraction."""

from app.fundamentals.base_provider import BaseFundamentalsProvider
from app.fundamentals.provider_factory import get_fundamentals_provider

__all__ = [
    "BaseFundamentalsProvider",
    "get_fundamentals_provider",
]
