"""Scheduler jobs for data ingestion and strategy execution."""

import asyncio
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import get_db_context
from app.core.logging import get_logger
from app.fundamentals.provider_factory import get_fundamentals_provider
from app.market_data.angel_one_client import AngelOneClient
from app.market_data.candle_manager import CandleManager
from app.market_data.instrument_cache import InstrumentCache
from app.models.strategy_run import StrategyRun
from app.scheduler.nse_calendar import NSECalendar
from app.strategies.fundamental_stockexploder import FundamentalStockexploderStrategy
from app.strategies.multibagger_technical import MultibaggerTechnicalStrategy
from app.strategies.rb_strategy import RBStrategy
from app.strategies.vcp_strategy import VCPStrategy
from app.telegram.alert_manager import AlertManager

logger = get_logger(__name__)


class SchedulerManager:
    """Manage scheduled jobs for data ingestion and strategy execution."""

    def __init__(self):
        """Initialize scheduler manager."""
        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
        self.nse_calendar = NSECalendar()
        self.instrument_cache = InstrumentCache()
        self.candle_manager = CandleManager()
        self.alert_manager = AlertManager()
        self.fundamentals_provider = get_fundamentals_provider()
        
        self._data_ready = False
        
        logger.info("Scheduler manager initialized")

    async def data_ingestion_job(self) -> None:
        """Ingest daily candle data from Angel One."""
        logger.info("Starting data ingestion job")
        
        try:
            # Check if today is a trading day
            if not self.nse_calendar.is_trading_day():
                logger.info("Not a trading day, skipping data ingestion")
                return
            
            async with get_db_context() as db:
                # Get all active instruments
                instruments = await self.instrument_cache.get_all_active_instruments(
                    db, exchange="NSE", instrument_type="EQ"
                )
                
                if not instruments:
                    logger.warning("No instruments found for data ingestion")
                    return
                
                logger.info(f"Ingesting data for {len(instruments)} instruments")
                
                # Ingest data for each instrument
                async with AngelOneClient() as client:
                    today = self.nse_calendar.get_current_date()
                    
                    for instrument in instruments:
                        try:
                            # Get latest candle date
                            latest_date = await self.candle_manager.get_latest_daily_candle_date(
                                db, instrument.token
                            )
                            
                            # Determine from_date
                            if latest_date:
                                from_date = self.nse_calendar.get_next_trading_day(latest_date)
                            else:
                                # First time ingestion - get last 100 days
                                from_date = today - timedelta(days=100)
                            
                            # Ingest daily candles
                            count = await self.candle_manager.ingest_daily_candles(
                                db, instrument, from_date, today, client
                            )
                            
                            if count > 0:
                                # Derive weekly and monthly candles
                                await self.candle_manager.derive_weekly_candles(
                                    db, instrument.token, from_date
                                )
                                await self.candle_manager.derive_monthly_candles(
                                    db, instrument.token, from_date
                                )
                            
                        except Exception as e:
                            logger.error(
                                "Error ingesting data for instrument",
                                symbol=instrument.symbol,
                                error=str(e),
                            )
                            continue
                
                await db.commit()
                
            logger.info("Data ingestion job completed")
            
        except Exception as e:
            logger.error("Data ingestion job failed", error=str(e))
            # Send health alert
            await self.alert_manager.send_health_alert(
                "Data Ingestion Failed",
                f"Error: {str(e)}",
            )

    async def data_ready_check_job(self) -> None:
        """Check if data is ready for strategy execution."""
        logger.info("Starting data ready check")
        
        try:
            if not self.nse_calendar.is_trading_day():
                logger.info("Not a trading day, skipping data ready check")
                self._data_ready = False
                return
            
            async with get_db_context() as db:
                today = self.nse_calendar.get_current_date()
                validation = await self.candle_manager.validate_data_ready(db, today)
                
                self._data_ready = validation["is_ready"]
                
                if self._data_ready:
                    logger.info("Data is ready for strategy execution")
                else:
                    logger.warning(
                        "Data not ready",
                        candles=validation["daily_candles_count"],
                        delayed=validation["delayed_count"],
                    )
                    
        except Exception as e:
            logger.error("Data ready check failed", error=str(e))
            self._data_ready = False

    async def run_strategy(
        self,
        strategy_class,
        signal_type: str = "candidate",
    ) -> None:
        """
        Run a strategy for all instruments.
        
        Args:
            strategy_class: Strategy class to instantiate
            signal_type: Signal type for this run
        """
        strategy = strategy_class()
        
        logger.info(
            "Starting strategy run",
            strategy=strategy.strategy_name,
            signal_type=signal_type,
        )
        
        try:
            # Check if data is ready
            if not self._data_ready:
                logger.warning(
                    "Data not ready, marking run as data_delayed",
                    strategy=strategy.strategy_name,
                )
            
            async with get_db_context() as db:
                # Create strategy run
                strategy_run = StrategyRun(
                    strategy_name=strategy.strategy_name,
                    strategy_version=strategy.strategy_version,
                    run_type="scheduled",
                    signal_date=self.nse_calendar.get_current_datetime(),
                    status="running" if self._data_ready else "data_delayed",
                    triggered_by="scheduler",
                )
                db.add(strategy_run)
                await db.flush()
                
                if not self._data_ready:
                    strategy_run.status = "data_delayed"
                    strategy_run.completed_at = datetime.utcnow()
                    await db.commit()
                    return
                
                # Get all active instruments
                instruments = await self.instrument_cache.get_all_active_instruments(
                    db, exchange="NSE", instrument_type="EQ"
                )
                
                strategy_run.symbols_scanned = len(instruments)
                
                # Evaluate strategy for each instrument
                results = []
                for instrument in instruments:
                    try:
                        result = await strategy.evaluate(
                            db, instrument.symbol, instrument.token
                        )
                        results.append(result)
                        
                        # Save signal
                        await strategy.save_signal(
                            db, strategy_run, result, signal_type
                        )
                        
                        if result.passed:
                            strategy_run.signals_passed += 1
                        else:
                            strategy_run.signals_failed += 1
                        
                    except Exception as e:
                        logger.error(
                            "Error evaluating strategy for instrument",
                            strategy=strategy.strategy_name,
                            symbol=instrument.symbol,
                            error=str(e),
                        )
                        strategy_run.signals_failed += 1
                        continue
                
                strategy_run.signals_generated = len(results)
                
                # Rank results
                passed_results = [r for r in results if r.passed]
                ranked_results = strategy.rank_results(passed_results)
                
                # Update strategy run
                strategy_run.status = "completed"
                strategy_run.completed_at = datetime.utcnow()
                strategy_run.duration_seconds = (
                    strategy_run.completed_at - strategy_run.started_at
                ).total_seconds()
                
                await db.commit()
                
                # Send alerts
                if ranked_results:
                    await self.alert_manager.send_strategy_alert(
                        strategy_run, ranked_results[:settings.telegram_max_symbols_in_message]
                    )
                
                logger.info(
                    "Strategy run completed",
                    strategy=strategy.strategy_name,
                    passed=len(ranked_results),
                    total=len(results),
                )
                
        except Exception as e:
            logger.error(
                "Strategy run failed",
                strategy=strategy.strategy_name,
                error=str(e),
            )
            
            # Update strategy run status
            async with get_db_context() as db:
                if 'strategy_run' in locals():
                    strategy_run.status = "failed"
                    strategy_run.error_message = str(e)
                    strategy_run.completed_at = datetime.utcnow()
                    await db.commit()
            
            # Send health alert
            await self.alert_manager.send_health_alert(
                f"Strategy Run Failed: {strategy.strategy_name}",
                f"Error: {str(e)}",
            )

    async def vcp_strategy_job(self) -> None:
        """Run VCP strategy."""
        if settings.enable_vcp_strategy:
            await self.run_strategy(VCPStrategy, signal_type="candidate")

    async def rb_daily_strategy_job(self) -> None:
        """Run RB strategy (daily watchlist)."""
        if settings.enable_rb_strategy:
            await self.run_strategy(RBStrategy, signal_type="watchlist")

    async def rb_monthly_strategy_job(self) -> None:
        """Run RB strategy (monthly confirmed)."""
        if settings.enable_rb_strategy:
            # Check if today is month-end trading day
            if self.nse_calendar.is_month_end_trading_day():
                await self.run_strategy(RBStrategy, signal_type="confirmed")

    async def multibagger_strategy_job(self) -> None:
        """Run Multi-bagger Technical strategy."""
        if settings.enable_multibagger_strategy:
            # Check if today is month-end trading day
            if self.nse_calendar.is_month_end_trading_day():
                await self.run_strategy(MultibaggerTechnicalStrategy, signal_type="candidate")

    async def fundamental_strategy_job(self) -> None:
        """Run Fundamental Stockexploder strategy."""
        if settings.enable_fundamental_strategy:
            # Check if today is month-end trading day
            if self.nse_calendar.is_month_end_trading_day():
                await self.run_strategy(FundamentalStockexploderStrategy, signal_type="candidate")

    async def telegram_retry_job(self) -> None:
        """Retry failed Telegram alerts."""
        logger.debug("Starting Telegram retry job")
        try:
            await self.alert_manager.retry_failed_alerts()
        except Exception as e:
            logger.error("Telegram retry job failed", error=str(e))

    def start(self) -> None:
        """Start the scheduler."""
        if not settings.enable_scheduler:
            logger.info("Scheduler disabled in configuration")
            return
        
        logger.info("Starting scheduler")
        
        # Data ingestion job (after market close)
        self.scheduler.add_job(
            self.data_ingestion_job,
            CronTrigger.from_crontab(
                f"{settings.data_ingestion_time.split(':')[1]} {settings.data_ingestion_time.split(':')[0]} * * 1-5",
                timezone=settings.scheduler_timezone,
            ),
            id="data_ingestion",
            name="Data Ingestion",
            replace_existing=True,
        )
        
        # Data ready check job
        self.scheduler.add_job(
            self.data_ready_check_job,
            CronTrigger.from_crontab(
                f"{settings.data_ready_check_time.split(':')[1]} {settings.data_ready_check_time.split(':')[0]} * * 1-5",
                timezone=settings.scheduler_timezone,
            ),
            id="data_ready_check",
            name="Data Ready Check",
            replace_existing=True,
        )
        
        # VCP strategy job
        self.scheduler.add_job(
            self.vcp_strategy_job,
            CronTrigger.from_crontab(
                f"{settings.vcp_scan_time.split(':')[1]} {settings.vcp_scan_time.split(':')[0]} * * 1-5",
                timezone=settings.scheduler_timezone,
            ),
            id="vcp_strategy",
            name="VCP Strategy",
            replace_existing=True,
        )
        
        # RB daily strategy job
        self.scheduler.add_job(
            self.rb_daily_strategy_job,
            CronTrigger.from_crontab(
                f"{settings.rb_daily_scan_time.split(':')[1]} {settings.rb_daily_scan_time.split(':')[0]} * * 1-5",
                timezone=settings.scheduler_timezone,
            ),
            id="rb_daily_strategy",
            name="RB Daily Strategy",
            replace_existing=True,
        )
        
        # Monthly strategies (RB confirmed, Multi-bagger, Fundamental)
        self.scheduler.add_job(
            self.rb_monthly_strategy_job,
            CronTrigger.from_crontab(
                f"{settings.monthly_scan_time.split(':')[1]} {settings.monthly_scan_time.split(':')[0]} * * 1-5",
                timezone=settings.scheduler_timezone,
            ),
            id="rb_monthly_strategy",
            name="RB Monthly Strategy",
            replace_existing=True,
        )
        
        self.scheduler.add_job(
            self.multibagger_strategy_job,
            CronTrigger.from_crontab(
                f"{settings.monthly_scan_time.split(':')[1]} {int(settings.monthly_scan_time.split(':')[0])+1} * * 1-5",
                timezone=settings.scheduler_timezone,
            ),
            id="multibagger_strategy",
            name="Multi-bagger Strategy",
            replace_existing=True,
        )
        
        self.scheduler.add_job(
            self.fundamental_strategy_job,
            CronTrigger.from_crontab(
                f"{settings.monthly_scan_time.split(':')[1]} {int(settings.monthly_scan_time.split(':')[0])+2} * * 1-5",
                timezone=settings.scheduler_timezone,
            ),
            id="fundamental_strategy",
            name="Fundamental Strategy",
            replace_existing=True,
        )
        
        # Telegram retry job (every 5 minutes)
        self.scheduler.add_job(
            self.telegram_retry_job,
            CronTrigger.from_crontab(
                "*/5 * * * *",
                timezone=settings.scheduler_timezone,
            ),
            id="telegram_retry",
            name="Telegram Retry",
            replace_existing=True,
        )
        
        self.scheduler.start()
        logger.info("Scheduler started", jobs=len(self.scheduler.get_jobs()))

    def stop(self) -> None:
        """Stop the scheduler."""
        logger.info("Stopping scheduler")
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    def get_jobs(self) -> list:
        """Get all scheduled jobs."""
        return self.scheduler.get_jobs()
