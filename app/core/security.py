"""API security and authentication."""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings

# API key header schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
admin_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify API key for standard endpoints.
    
    Args:
        api_key: API key from header
        
    Returns:
        Verified API key
        
    Raises:
        HTTPException: If API key is invalid
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key is missing",
        )
    
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )
    
    return api_key


async def verify_admin_api_key(api_key: str = Security(admin_api_key_header)) -> str:
    """
    Verify admin API key for administrative endpoints.
    
    Args:
        api_key: Admin API key from header
        
    Returns:
        Verified admin API key
        
    Raises:
        HTTPException: If admin API key is invalid
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Admin API key is missing",
        )
    
    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin API key",
        )
    
    return api_key
