"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.logging import get_logger
from app.scheduler.jobs import SchedulerManager

logger = get_logger(__name__)

# Global scheduler instance
scheduler_manager: SchedulerManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting NSE Strategy Alerts application")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Start scheduler
        global scheduler_manager
        if settings.enable_scheduler:
            scheduler_manager = SchedulerManager()
            scheduler_manager.start()
            logger.info("Scheduler started")
        else:
            logger.info("Scheduler disabled in configuration")
        
        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error("Application startup failed", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down NSE Strategy Alerts application")
    
    try:
        # Stop scheduler
        if scheduler_manager:
            scheduler_manager.stop()
            logger.info("Scheduler stopped")
        
        # Close database connections
        await close_db()
        logger.info("Database connections closed")
        
        logger.info("Application shutdown complete")
        
    except Exception as e:
        logger.error("Application shutdown error", error=str(e))


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Alert-only NSE stock screening system - No auto-trading",
    lifespan=lifespan,
    debug=settings.debug,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "Alert-only NSE stock screening system",
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
