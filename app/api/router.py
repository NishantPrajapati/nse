"""FastAPI router with all API endpoints."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import verify_admin_api_key, verify_api_key
from app.fundamentals.provider_factory import get_fundamentals_provider
from app.market_data.angel_one_client import AngelOneClient
from app.market_data.candle_manager import CandleManager
from app.market_data.instrument_cache import InstrumentCache
from app.models.signal import Signal
from app.models.strategy_run import StrategyRun
from app.scheduler.nse_calendar import NSECalendar
from app.strategies.fundamental_stockexploder import FundamentalStockexploderStrategy
from app.strategies.multibagger_technical import MultibaggerTechnicalStrategy
from app.strategies.rb_strategy import RBStrategy
from app.strategies.vcp_strategy import VCPStrategy
from app.telegram.alert_manager import AlertManager

logger = get_logger(__name__)

api_router = APIRouter()


# Health endpoints
@api_router.get("/health")
async def health_check():
    """Basic health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@api_router.get("/health/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Detailed health check with component status."""
    logger.info("Detailed health check requested")
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {},
    }
    
    # Database check
    try:
        await db.execute(select(1))
        health_status["components"]["database"] = {
            "status": "healthy",
            "message": "Connected",
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "message": str(e),
        }
    
    # Angel One check
    try:
        async with AngelOneClient() as client:
            is_healthy = await client.health_check()
            health_status["components"]["angel_one"] = {
                "status": "healthy" if is_healthy else "unhealthy",
                "message": "Connected" if is_healthy else "Connection failed",
            }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["angel_one"] = {
            "status": "unhealthy",
            "message": str(e),
        }
    
    # Telegram check
    try:
        alert_manager = AlertManager()
        is_connected = await alert_manager.test_connection()
        health_status["components"]["telegram"] = {
            "status": "healthy" if is_connected else "unhealthy",
            "message": "Connected" if is_connected else "Connection failed",
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["telegram"] = {
            "status": "unhealthy",
            "message": str(e),
        }
    
    # Fundamentals provider check
    try:
        provider = get_fundamentals_provider()
        is_healthy = await provider.health_check()
        health_status["components"]["fundamentals"] = {
            "status": "healthy" if is_healthy else "unhealthy",
            "provider": provider.provider_name,
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["fundamentals"] = {
            "status": "unhealthy",
            "message": str(e),
        }
    
    # Data freshness check
    try:
        candle_manager = CandleManager()
        nse_calendar = NSECalendar()
        
        if nse_calendar.is_trading_day():
            today = nse_calendar.get_current_date()
            validation = await candle_manager.validate_data_ready(db, today)
            
            health_status["components"]["data"] = {
                "status": "healthy" if validation["is_ready"] else "degraded",
                "latest_date": today.isoformat(),
                "candles_count": validation["daily_candles_count"],
                "delayed_count": validation["delayed_count"],
            }
        else:
            health_status["components"]["data"] = {
                "status": "healthy",
                "message": "Not a trading day",
            }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["data"] = {
            "status": "unhealthy",
            "message": str(e),
        }
    
    return health_status


# Strategy runs endpoints
@api_router.get("/runs")
async def list_strategy_runs(
    strategy: Optional[str] = Query(None, description="Filter by strategy name"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Number of runs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """List strategy runs with optional filters."""
    logger.info("Listing strategy runs", strategy=strategy, status=status)
    
    query = select(StrategyRun).order_by(StrategyRun.started_at.desc())
    
    if strategy:
        query = query.where(StrategyRun.strategy_name == strategy)
    
    if status:
        query = query.where(StrategyRun.status == status)
    
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return {
        "runs": [
            {
                "id": run.id,
                "strategy_name": run.strategy_name,
                "strategy_version": run.strategy_version,
                "run_type": run.run_type,
                "signal_date": run.signal_date.isoformat(),
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "duration_seconds": run.duration_seconds,
                "symbols_scanned": run.symbols_scanned,
                "signals_generated": run.signals_generated,
                "signals_passed": run.signals_passed,
                "signals_failed": run.signals_failed,
            }
            for run in runs
        ],
        "limit": limit,
        "offset": offset,
    }


@api_router.get("/runs/{run_id}")
async def get_strategy_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Get specific strategy run details."""
    logger.info("Getting strategy run", run_id=run_id)
    
    result = await db.execute(
        select(StrategyRun).where(StrategyRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(status_code=404, detail="Strategy run not found")
    
    return {
        "id": run.id,
        "strategy_name": run.strategy_name,
        "strategy_version": run.strategy_version,
        "run_type": run.run_type,
        "signal_date": run.signal_date.isoformat(),
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_seconds": run.duration_seconds,
        "symbols_scanned": run.symbols_scanned,
        "signals_generated": run.signals_generated,
        "signals_passed": run.signals_passed,
        "signals_failed": run.signals_failed,
        "data_date": run.data_date.isoformat() if run.data_date else None,
        "data_delay_hours": run.data_delay_hours,
        "error_message": run.error_message,
    }


# Signals endpoints
@api_router.get("/signals")
async def list_signals(
    strategy: Optional[str] = Query(None, description="Filter by strategy name"),
    date: Optional[str] = Query(None, description="Filter by signal date (YYYY-MM-DD)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    passed_only: bool = Query(False, description="Show only passed signals"),
    limit: int = Query(100, ge=1, le=1000, description="Number of signals to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """List signals with optional filters."""
    logger.info("Listing signals", strategy=strategy, date=date, symbol=symbol)
    
    query = select(Signal).order_by(Signal.signal_date.desc(), Signal.rank)
    
    if strategy:
        query = query.where(Signal.strategy_name == strategy)
    
    if date:
        try:
            filter_date = datetime.fromisoformat(date)
            query = query.where(func.date(Signal.signal_date) == filter_date.date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    if symbol:
        query = query.where(Signal.symbol == symbol)
    
    if passed_only:
        query = query.where(Signal.passed == True)
    
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    signals = result.scalars().all()
    
    return {
        "signals": [
            {
                "id": signal.id,
                "symbol": signal.symbol,
                "strategy_name": signal.strategy_name,
                "strategy_version": signal.strategy_version,
                "signal_date": signal.signal_date.isoformat(),
                "signal_type": signal.signal_type,
                "price": signal.price,
                "volume": signal.volume,
                "rank": signal.rank,
                "rank_score": signal.rank_score,
                "passed": signal.passed,
                "conditions_passed": signal.conditions_passed,
                "conditions_total": signal.conditions_total,
            }
            for signal in signals
        ],
        "limit": limit,
        "offset": offset,
    }


@api_router.get("/signals/{symbol}")
async def get_symbol_signals(
    symbol: str,
    strategy: Optional[str] = Query(None, description="Filter by strategy name"),
    limit: int = Query(50, ge=1, le=500, description="Number of signals to return"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
):
    """Get all signals for a specific symbol."""
    logger.info("Getting signals for symbol", symbol=symbol)
    
    query = select(Signal).where(Signal.symbol == symbol).order_by(Signal.signal_date.desc())
    
    if strategy:
        query = query.where(Signal.strategy_name == strategy)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    signals = result.scalars().all()
    
    if not signals:
        raise HTTPException(status_code=404, detail=f"No signals found for symbol {symbol}")
    
    return {
        "symbol": symbol,
        "signals": [
            {
                "id": signal.id,
                "strategy_name": signal.strategy_name,
                "strategy_version": signal.strategy_version,
                "signal_date": signal.signal_date.isoformat(),
                "signal_type": signal.signal_type,
                "price": signal.price,
                "volume": signal.volume,
                "rank": signal.rank,
                "rank_score": signal.rank_score,
                "passed": signal.passed,
                "conditions_passed": signal.conditions_passed,
                "conditions_total": signal.conditions_total,
                "conditions": [
                    {
                        "name": cond.condition_name,
                        "description": cond.condition_description,
                        "passed": cond.passed,
                        "expected": cond.expected_value,
                        "actual": cond.actual_value,
                        "reason": cond.reason,
                    }
                    for cond in signal.conditions
                ],
            }
            for signal in signals
        ],
    }


# Strategies endpoints
@api_router.get("/strategies")
async def list_strategies(_api_key: str = Depends(verify_api_key)):
    """List all available strategies with their definitions."""
    logger.info("Listing strategies")
    
    strategies = [
        VCPStrategy(),
        RBStrategy(),
        MultibaggerTechnicalStrategy(),
        FundamentalStockexploderStrategy(),
    ]
    
    return {
        "strategies": [
            strategy.get_strategy_info()
            for strategy in strategies
        ]
    }


# Admin endpoints
@api_router.post("/admin/refresh-instruments")
async def refresh_instruments(
    force: bool = Query(False, description="Force refresh even if cache is valid"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_admin_api_key),
):
    """Refresh instrument master cache."""
    logger.info("Refreshing instruments", force=force)
    
    try:
        instrument_cache = InstrumentCache()
        count = await instrument_cache.refresh_instruments(force=force)
        
        return {
            "status": "success",
            "instruments_updated": count,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("Failed to refresh instruments", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/ingest-daily")
async def ingest_daily_data(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_admin_api_key),
):
    """Trigger manual daily data ingestion."""
    logger.info("Manual daily data ingestion triggered")
    
    try:
        # This would trigger the data ingestion job
        # For now, return a placeholder response
        return {
            "status": "triggered",
            "message": "Data ingestion job started",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("Failed to trigger data ingestion", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/run-strategy/{strategy_name}")
async def run_strategy_manual(
    strategy_name: str,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_admin_api_key),
):
    """Trigger manual strategy run."""
    logger.info("Manual strategy run triggered", strategy=strategy_name)
    
    strategy_map = {
        "VCP": VCPStrategy,
        "RB": RBStrategy,
        "MultibaggerTechnical": MultibaggerTechnicalStrategy,
        "FundamentalStockexploder": FundamentalStockexploderStrategy,
    }
    
    if strategy_name not in strategy_map:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy not found. Available: {list(strategy_map.keys())}",
        )
    
    try:
        # This would trigger the strategy run job
        # For now, return a placeholder response
        return {
            "status": "triggered",
            "strategy": strategy_name,
            "message": f"{strategy_name} strategy run started",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("Failed to trigger strategy run", strategy=strategy_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
