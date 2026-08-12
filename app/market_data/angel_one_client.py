"""Angel One SmartAPI client with TOTP authentication and rate limiting."""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import pyotp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, calls: int, period: int):
        """
        Initialize rate limiter.
        
        Args:
            calls: Number of calls allowed per period
            period: Time period in seconds
        """
        self.calls = calls
        self.period = period
        self.tokens = calls
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.calls,
                self.tokens + (elapsed * self.calls / self.period)
            )
            self.last_update = now
            
            # Wait if no tokens available
            if self.tokens < 1:
                wait_time = (1 - self.tokens) * self.period / self.calls
                logger.debug("Rate limit reached, waiting", wait_seconds=wait_time)
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class AngelOneClient:
    """Angel One SmartAPI client with authentication and rate limiting."""

    BASE_URL = "https://apiconnect.angelbroking.com"
    
    def __init__(self):
        """Initialize Angel One client."""
        self.api_key = settings.angel_api_key
        self.client_id = settings.angel_client_id
        self.password = settings.angel_password
        self.totp_secret = settings.angel_totp_secret
        
        self.session_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.feed_token: Optional[str] = None
        self.session_expiry: Optional[datetime] = None
        
        self.rate_limiter = RateLimiter(
            calls=settings.angel_rate_limit_calls,
            period=settings.angel_rate_limit_period,
        )
        
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        
        logger.info("Angel One client initialized")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.angel_api_timeout,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-UserType": "USER",
                    "X-SourceID": "WEB",
                }
            )
            logger.info("HTTP client connected")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client closed")

    def _generate_totp(self) -> str:
        """Generate TOTP code from secret."""
        try:
            totp = pyotp.TOTP(self.totp_secret)
            code = totp.now()
            logger.debug("TOTP generated successfully")
            return code
        except Exception as e:
            logger.error("TOTP generation failed", error=str(e))
            raise

    async def _is_session_valid(self) -> bool:
        """Check if current session is valid."""
        if not self.session_token:
            return False
        
        if not self.session_expiry:
            return False
        
        # Consider session invalid 5 minutes before actual expiry
        buffer = timedelta(minutes=5)
        return datetime.utcnow() < (self.session_expiry - buffer)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def authenticate(self) -> dict[str, Any]:
        """
        Authenticate with Angel One using TOTP.
        
        Returns:
            Authentication response with tokens
            
        Raises:
            Exception: If authentication fails
        """
        async with self._lock:
            # Check if session is still valid
            if await self._is_session_valid():
                logger.debug("Using existing valid session")
                return {
                    "status": True,
                    "message": "Session already valid",
                    "data": {
                        "jwtToken": self.session_token,
                        "refreshToken": self.refresh_token,
                        "feedToken": self.feed_token,
                    }
                }
            
            logger.info("Authenticating with Angel One")
            
            if not self._client:
                await self.connect()
            
            totp_code = self._generate_totp()
            
            payload = {
                "clientcode": self.client_id,
                "password": self.password,
                "totp": totp_code,
            }
            
            try:
                response = await self._client.post(
                    f"{self.BASE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
                    json=payload,
                    headers={"X-PrivateKey": self.api_key},
                )
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("status") and data.get("data"):
                    self.session_token = data["data"].get("jwtToken")
                    self.refresh_token = data["data"].get("refreshToken")
                    self.feed_token = data["data"].get("feedToken")
                    
                    # Angel One sessions typically last 24 hours
                    self.session_expiry = datetime.utcnow() + timedelta(hours=23)
                    
                    logger.info(
                        "Authentication successful",
                        expiry=self.session_expiry.isoformat(),
                    )
                    return data
                else:
                    error_msg = data.get("message", "Unknown error")
                    logger.error("Authentication failed", error=error_msg)
                    raise Exception(f"Authentication failed: {error_msg}")
                    
            except httpx.HTTPStatusError as e:
                logger.error(
                    "Authentication HTTP error",
                    status_code=e.response.status_code,
                    response=e.response.text,
                )
                raise
            except Exception as e:
                logger.error("Authentication error", error=str(e))
                raise

    async def _ensure_authenticated(self) -> None:
        """Ensure client is authenticated before making API calls."""
        if not await self._is_session_valid():
            await self.authenticate()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> dict[str, Any]:
        """
        Make authenticated API request with rate limiting.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional request parameters
            
        Returns:
            API response data
        """
        await self._ensure_authenticated()
        await self.rate_limiter.acquire()
        
        if not self._client:
            await self.connect()
        
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {self.session_token}",
            "X-PrivateKey": self.api_key,
        })
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = await self._client.request(
                method,
                url,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(
                "API request failed",
                method=method,
                endpoint=endpoint,
                status_code=e.response.status_code,
                response=e.response.text,
            )
            raise
        except Exception as e:
            logger.error(
                "API request error",
                method=method,
                endpoint=endpoint,
                error=str(e),
            )
            raise

    async def get_profile(self) -> dict[str, Any]:
        """Get user profile."""
        logger.debug("Fetching user profile")
        return await self._make_request(
            "GET",
            "/rest/secure/angelbroking/user/v1/getProfile"
        )

    async def get_all_holdings(self) -> dict[str, Any]:
        """Get all holdings."""
        logger.debug("Fetching holdings")
        return await self._make_request(
            "GET",
            "/rest/secure/angelbroking/portfolio/v1/getAllHolding"
        )

    async def search_scrip(self, exchange: str, symbol: str) -> dict[str, Any]:
        """
        Search for scrip by symbol.
        
        Args:
            exchange: Exchange (NSE, BSE, etc.)
            symbol: Symbol to search
            
        Returns:
            Scrip details
        """
        logger.debug("Searching scrip", exchange=exchange, symbol=symbol)
        return await self._make_request(
            "POST",
            "/rest/secure/angelbroking/order/v1/searchScrip",
            json={"exchange": exchange, "searchscrip": symbol}
        )

    async def get_candle_data(
        self,
        exchange: str,
        symbol_token: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> dict[str, Any]:
        """
        Get historical candle data.
        
        Args:
            exchange: Exchange (NSE, BSE, etc.)
            symbol_token: Symbol token
            interval: Candle interval (ONE_DAY, ONE_WEEK, ONE_MONTH)
            from_date: Start date (YYYY-MM-DD HH:MM)
            to_date: End date (YYYY-MM-DD HH:MM)
            
        Returns:
            Candle data
        """
        logger.debug(
            "Fetching candle data",
            exchange=exchange,
            token=symbol_token,
            interval=interval,
            from_date=from_date,
            to_date=to_date,
        )
        
        return await self._make_request(
            "POST",
            "/rest/secure/angelbroking/historical/v1/getCandleData",
            json={
                "exchange": exchange,
                "symboltoken": symbol_token,
                "interval": interval,
                "fromdate": from_date,
                "todate": to_date,
            }
        )

    async def get_ltp_data(
        self,
        exchange: str,
        trading_symbol: str,
        symbol_token: str,
    ) -> dict[str, Any]:
        """
        Get last traded price.
        
        Args:
            exchange: Exchange
            trading_symbol: Trading symbol
            symbol_token: Symbol token
            
        Returns:
            LTP data
        """
        logger.debug(
            "Fetching LTP",
            exchange=exchange,
            symbol=trading_symbol,
            token=symbol_token,
        )
        
        return await self._make_request(
            "POST",
            "/rest/secure/angelbroking/market/v1/quote/",
            json={
                "mode": "LTP",
                "exchangeTokens": {
                    exchange: [symbol_token]
                }
            }
        )

    async def logout(self) -> dict[str, Any]:
        """Logout and invalidate session."""
        logger.info("Logging out")
        
        try:
            response = await self._make_request(
                "POST",
                "/rest/secure/angelbroking/user/v1/logout",
                json={"clientcode": self.client_id}
            )
            
            # Clear session data
            self.session_token = None
            self.refresh_token = None
            self.feed_token = None
            self.session_expiry = None
            
            logger.info("Logout successful")
            return response
            
        except Exception as e:
            logger.error("Logout error", error=str(e))
            raise

    async def health_check(self) -> bool:
        """
        Check if Angel One API is accessible and authenticated.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            await self._ensure_authenticated()
            profile = await self.get_profile()
            return profile.get("status", False)
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return False
