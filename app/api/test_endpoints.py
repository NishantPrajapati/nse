"""Test endpoints for manual testing."""

from fastapi import APIRouter, Depends

from app.core.logging import get_logger
from app.core.security import verify_admin_api_key
from app.telegram.alert_manager import AlertManager

logger = get_logger(__name__)

test_router = APIRouter(prefix="/test", tags=["test"])


@test_router.post("/telegram")
async def test_telegram(
    _api_key: str = Depends(verify_admin_api_key),
):
    """Send a test message to Telegram."""
    logger.info("Telegram test requested")
    
    alert_manager = AlertManager()
    
    # Test connection
    is_connected = await alert_manager.test_connection()
    
    if not is_connected:
        return {
            "status": "error",
            "message": "Failed to connect to Telegram bot",
        }
    
    # Send test message
    success = await alert_manager.send_health_alert(
        title="NSE Strategy Alerts - Test Message",
        message="🎉 Application is running successfully!\n\n"
                "✅ Database: Connected\n"
                "✅ Scheduler: Running (8 jobs)\n"
                "✅ Telegram: Connected\n"
                "✅ Angel One API: Ready\n\n"
                "This is a test message to verify Telegram integration."
    )
    
    if success:
        return {
            "status": "success",
            "message": "Test message sent successfully! Check your Telegram chat.",
        }
    else:
        return {
            "status": "error",
            "message": "Failed to send test message",
        }
