"""Telegram alert manager for sending and tracking alerts."""

import asyncio
import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from telegram.error import TelegramError

from app.core.config import settings
from app.core.database import get_db_context
from app.core.logging import get_logger
from app.models.strategy_run import StrategyRun
from app.models.telegram_alert import TelegramAlert
from app.strategies.base_strategy import StrategyResult

logger = get_logger(__name__)


class AlertManager:
    """Manage Telegram alert delivery with deduplication and retry logic."""

    def __init__(self):
        """Initialize alert manager."""
        self.bot = Bot(token=settings.telegram_bot_token)
        self.chat_id = settings.telegram_chat_id
        self.max_message_length = settings.telegram_max_message_length
        self.max_symbols = settings.telegram_max_symbols_in_message
        
        logger.info(
            "Alert manager initialized",
            chat_id=settings.telegram_chat_id[:8] + "***",
        )

    async def check_duplicate(
        self,
        db: AsyncSession,
        strategy_name: str,
        strategy_version: str,
        signal_date: datetime,
        alert_type: str,
        symbol: Optional[str] = None,
    ) -> bool:
        """
        Check if alert already exists (deduplication).
        
        Args:
            db: Database session
            strategy_name: Strategy name
            strategy_version: Strategy version
            signal_date: Signal date
            alert_type: Alert type
            symbol: Symbol (optional, for individual alerts)
            
        Returns:
            True if duplicate exists
        """
        result = await db.execute(
            select(TelegramAlert).where(
                and_(
                    TelegramAlert.strategy_name == strategy_name,
                    TelegramAlert.strategy_version == strategy_version,
                    TelegramAlert.signal_date == signal_date,
                    TelegramAlert.alert_type == alert_type,
                    TelegramAlert.symbol == symbol,
                )
            )
        )
        
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.debug(
                "Duplicate alert found",
                strategy=strategy_name,
                alert_type=alert_type,
                symbol=symbol,
            )
            return True
        
        return False

    def format_strategy_message(
        self,
        strategy_run: StrategyRun,
        results: list[StrategyResult],
    ) -> str:
        """
        Format strategy results as Telegram message.
        
        Args:
            strategy_run: Strategy run instance
            results: List of strategy results (ranked)
            
        Returns:
            Formatted message text
        """
        # Emoji mapping
        emoji_map = {
            "VCP": "🎯",
            "RB": "🚀",
            "MultibaggerTechnical": "💎",
            "FundamentalStockexploder": "⭐",
        }
        
        emoji = emoji_map.get(strategy_run.strategy_name, "📊")
        
        # Header
        lines = [
            f"{emoji} **{strategy_run.strategy_name} Candidates** - {strategy_run.signal_date.strftime('%Y-%m-%d')}",
            f"Strategy Version: v{strategy_run.strategy_version}",
            f"Data Date: {strategy_run.data_date.strftime('%Y-%m-%d %H:%M IST') if strategy_run.data_date else 'N/A'}",
            "",
        ]
        
        # Top candidates
        display_count = min(len(results), self.max_symbols)
        lines.append(f"Top {display_count} Candidates:")
        
        for i, result in enumerate(results[:display_count], 1):
            # Star rating based on rank score
            stars = "⭐" * min(5, int(result.rank_score / 20))
            
            lines.append(f"{i}. **{result.symbol}** (₹{result.price:.2f}) {stars}")
            
            # Show passed conditions
            passed_conditions = [c for c in result.conditions if c.passed]
            if passed_conditions:
                for cond in passed_conditions[:3]:  # Show top 3
                    lines.append(f"   ✓ {cond.name}")
            
            # Show failed conditions if any
            failed_conditions = [c for c in result.conditions if not c.passed]
            if failed_conditions and len(failed_conditions) <= 2:
                for cond in failed_conditions:
                    lines.append(f"   ✗ {cond.name}")
            
            lines.append("")
        
        # Summary
        if len(results) > display_count:
            lines.append(f"[Full list: {len(results)} symbols - see attachment]")
            lines.append("")
        
        # Disclaimer
        lines.extend([
            "⚠️ **SCREENING CANDIDATES ONLY - NOT BUY SIGNALS**",
            f"📊 Data freshness: {'✓ Current' if strategy_run.data_delay_hours and strategy_run.data_delay_hours < 2 else '⚠️ Delayed'}",
        ])
        
        return "\n".join(lines)

    def generate_csv_attachment(
        self,
        results: list[StrategyResult],
    ) -> io.BytesIO:
        """
        Generate CSV attachment for full results.
        
        Args:
            results: List of strategy results
            
        Returns:
            CSV file as BytesIO
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Rank",
            "Symbol",
            "Price",
            "Volume",
            "Rank Score",
            "Conditions Passed",
            "Conditions Total",
            "Data Date",
        ])
        
        # Data rows
        for result in results:
            writer.writerow([
                getattr(result, 'rank', 0),
                result.symbol,
                f"{result.price:.2f}",
                result.volume,
                f"{result.rank_score:.2f}",
                result.conditions_passed,
                result.conditions_total,
                result.data_date.strftime("%Y-%m-%d"),
            ])
        
        # Convert to BytesIO
        output.seek(0)
        bytes_output = io.BytesIO(output.getvalue().encode('utf-8'))
        bytes_output.name = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return bytes_output

    async def send_strategy_alert(
        self,
        strategy_run: StrategyRun,
        results: list[StrategyResult],
    ) -> bool:
        """
        Send strategy alert to Telegram.
        
        Args:
            strategy_run: Strategy run instance
            results: List of strategy results (ranked)
            
        Returns:
            True if sent successfully
        """
        logger.info(
            "Sending strategy alert",
            strategy=strategy_run.strategy_name,
            candidates=len(results),
        )
        
        try:
            async with get_db_context() as db:
                # Check for duplicate
                is_duplicate = await self.check_duplicate(
                    db,
                    strategy_run.strategy_name,
                    strategy_run.strategy_version,
                    strategy_run.signal_date,
                    "summary",
                )
                
                if is_duplicate:
                    logger.info("Duplicate alert, skipping")
                    return True
                
                # Format message
                message_text = self.format_strategy_message(strategy_run, results)
                
                # Create alert record
                alert = TelegramAlert(
                    strategy_run_id=strategy_run.id,
                    strategy_name=strategy_run.strategy_name,
                    strategy_version=strategy_run.strategy_version,
                    signal_date=strategy_run.signal_date,
                    alert_type="summary",
                    message_text=message_text,
                    message_length=len(message_text),
                    has_attachment=len(results) > self.max_symbols,
                    status="pending",
                )
                
                db.add(alert)
                await db.flush()
                
                # Send message
                try:
                    # Send text message
                    response = await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=message_text,
                        parse_mode="Markdown",
                    )
                    
                    alert.telegram_message_id = response.message_id
                    alert.telegram_chat_id = str(response.chat_id)
                    alert.status = "sent"
                    alert.sent_at = datetime.utcnow()
                    alert.attempt_count = 1
                    
                    # Send CSV attachment if needed
                    if len(results) > self.max_symbols:
                        csv_file = self.generate_csv_attachment(results)
                        
                        await self.bot.send_document(
                            chat_id=self.chat_id,
                            document=csv_file,
                            filename=f"{strategy_run.strategy_name}_{strategy_run.signal_date.strftime('%Y%m%d')}.csv",
                            caption=f"Full results for {strategy_run.strategy_name}",
                        )
                        
                        alert.attachment_filename = csv_file.name
                    
                    logger.info(
                        "Strategy alert sent successfully",
                        strategy=strategy_run.strategy_name,
                        message_id=response.message_id,
                    )
                    
                except TelegramError as e:
                    logger.error(
                        "Failed to send Telegram message",
                        strategy=strategy_run.strategy_name,
                        error=str(e),
                    )
                    
                    alert.status = "failed"
                    alert.error_message = str(e)
                    alert.last_error_at = datetime.utcnow()
                    alert.attempt_count = 1
                    alert.next_retry_at = datetime.utcnow() + timedelta(
                        seconds=settings.telegram_retry_delay
                    )
                    
                    await db.commit()
                    return False
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(
                "Error sending strategy alert",
                strategy=strategy_run.strategy_name,
                error=str(e),
            )
            return False

    async def send_health_alert(
        self,
        title: str,
        message: str,
    ) -> bool:
        """
        Send health/error alert to Telegram.
        
        Args:
            title: Alert title
            message: Alert message
            
        Returns:
            True if sent successfully
        """
        logger.info("Sending health alert", title=title)
        
        try:
            alert_text = f"🚨 **{title}**\n\n{message}\n\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            
            response = await self.bot.send_message(
                chat_id=self.chat_id,
                text=alert_text,
                parse_mode="Markdown",
            )
            
            logger.info("Health alert sent", message_id=response.message_id)
            return True
            
        except TelegramError as e:
            logger.error("Failed to send health alert", error=str(e))
            return False

    async def retry_failed_alerts(self) -> int:
        """
        Retry failed Telegram alerts.
        
        Returns:
            Number of alerts retried
        """
        logger.debug("Checking for failed alerts to retry")
        
        try:
            async with get_db_context() as db:
                # Get failed alerts ready for retry
                now = datetime.utcnow()
                
                result = await db.execute(
                    select(TelegramAlert).where(
                        and_(
                            TelegramAlert.status.in_(["failed", "retrying"]),
                            TelegramAlert.attempt_count < TelegramAlert.max_attempts,
                            TelegramAlert.next_retry_at <= now,
                        )
                    )
                )
                
                alerts = result.scalars().all()
                
                if not alerts:
                    return 0
                
                logger.info(f"Retrying {len(alerts)} failed alerts")
                
                retry_count = 0
                for alert in alerts:
                    try:
                        # Send message
                        response = await self.bot.send_message(
                            chat_id=self.chat_id,
                            text=alert.message_text,
                            parse_mode="Markdown",
                        )
                        
                        alert.telegram_message_id = response.message_id
                        alert.telegram_chat_id = str(response.chat_id)
                        alert.status = "sent"
                        alert.sent_at = datetime.utcnow()
                        alert.attempt_count += 1
                        
                        retry_count += 1
                        
                        logger.info(
                            "Alert retry successful",
                            alert_id=alert.id,
                            attempt=alert.attempt_count,
                        )
                        
                    except TelegramError as e:
                        logger.error(
                            "Alert retry failed",
                            alert_id=alert.id,
                            attempt=alert.attempt_count + 1,
                            error=str(e),
                        )
                        
                        alert.status = "retrying"
                        alert.error_message = str(e)
                        alert.last_error_at = datetime.utcnow()
                        alert.attempt_count += 1
                        
                        # Exponential backoff
                        delay = settings.telegram_retry_delay * (2 ** alert.attempt_count)
                        alert.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                        
                        # Mark as failed if max attempts reached
                        if alert.attempt_count >= alert.max_attempts:
                            alert.status = "failed"
                            logger.warning(
                                "Alert max retries reached",
                                alert_id=alert.id,
                                attempts=alert.attempt_count,
                            )
                
                await db.commit()
                
                logger.info(f"Retry complete: {retry_count}/{len(alerts)} successful")
                return retry_count
                
        except Exception as e:
            logger.error("Error retrying failed alerts", error=str(e))
            return 0

    async def test_connection(self) -> bool:
        """
        Test Telegram bot connection.
        
        Returns:
            True if connection successful
        """
        try:
            me = await self.bot.get_me()
            logger.info(
                "Telegram connection test successful",
                bot_username=me.username,
            )
            return True
        except TelegramError as e:
            logger.error("Telegram connection test failed", error=str(e))
            return False
