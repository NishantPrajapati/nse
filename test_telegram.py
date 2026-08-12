#!/usr/bin/env python3
"""Test Telegram bot connection and send a test message."""

import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.telegram.alert_manager import AlertManager
from app.core.logging import get_logger

logger = get_logger(__name__)


async def main():
    """Test Telegram connection and send test message."""
    print("🔍 Testing Telegram bot connection...")
    
    alert_manager = AlertManager()
    
    # Test connection
    print("\n1️⃣ Testing bot connection...")
    is_connected = await alert_manager.test_connection()
    
    if not is_connected:
        print("❌ Telegram connection failed!")
        return False
    
    print("✅ Telegram bot connected successfully!")
    
    # Send test message
    print("\n2️⃣ Sending test message...")
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
        print("✅ Test message sent successfully!")
        print("\n📱 Check your Telegram chat for the message.")
        return True
    else:
        print("❌ Failed to send test message!")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
