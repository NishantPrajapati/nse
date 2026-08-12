# NSE Strategy Alerts

**Alert-Only Stock Screening System** - No Auto-Trading

A production-grade system that evaluates four named NSE stock screening strategies on their correct schedules and sends deduplicated candidate lists to Telegram. This system **never** places, modifies, or cancels broker orders.

## Features

- **Four Proven Strategies**: VCP, RB (Rocket Base), Multi-bagger Technical, Fundamental Stockexploder
- **Scheduled Execution**: Automatic daily, weekly, and monthly scans based on NSE trading calendar
- **Data Integrity**: Never uses incomplete candles; validates data freshness
- **Telegram Alerts**: Compact summaries with CSV attachments for longer lists
- **Audit Trail**: Complete condition evaluation history for every symbol
- **Provider Abstraction**: Pluggable fundamentals data sources
- **Parity Testing**: Validate against manually exported screen results

## Architecture

```
nse-strategy-alerts/
├── app/
│   ├── api/              # FastAPI endpoints
│   ├── core/             # Configuration, security, database
│   ├── market_data/      # Angel One integration, candle management
│   ├── fundamentals/     # Provider interface, data models
│   ├── strategies/       # Strategy implementations
│   ├── scheduler/        # APScheduler jobs, NSE calendar
│   ├── telegram/         # Alert delivery, deduplication
│   └── models/           # SQLAlchemy models
├── tests/                # Unit and integration tests
├── alembic/              # Database migrations
├── docs/                 # Additional documentation
└── deployment/           # Podman Compose configs
```

## Stack

- **Python 3.12**
- **FastAPI** - Modern async web framework
- **PostgreSQL** - Relational database
- **SQLAlchemy 2.0** - ORM with async support
- **Alembic** - Database migrations
- **APScheduler** - Job scheduling
- **Angel One SmartAPI** - Market data source
- **Telegram Bot API** - Alert delivery
- **Podman Compose** - Container orchestration

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Podman or Docker
- Angel One trading account with API access
- Telegram bot token

### Installation

1. Clone and setup:
```bash
cd nse-strategy-alerts
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Initialize database:
```bash
alembic upgrade head
```

4. Run development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Deployment (Podman Compose)

```bash
cd deployment
podman-compose up -d
```

## Configuration

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/nse_alerts

# Angel One API
ANGEL_API_KEY=your_api_key
ANGEL_CLIENT_ID=your_client_id
ANGEL_PASSWORD=your_password
ANGEL_TOTP_SECRET=your_totp_secret

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Fundamentals Provider (optional, defaults to mock)
FUNDAMENTALS_PROVIDER=angel_one  # or 'mock' for testing

# Scheduler
SCHEDULER_TIMEZONE=Asia/Kolkata
ENABLE_SCHEDULER=true
```

## Strategy Schedules

| Strategy | Schedule | Trigger |
|----------|----------|---------|
| VCP | Daily EOD | After data-ready validation |
| RB Watchlist | Daily EOD | After data-ready validation |
| RB Confirmed | Month-end | After final monthly candle closes |
| Multi-bagger Technical | Month-end | After final monthly candle closes |
| Fundamental Stockexploder | Month-end | After fundamentals refresh |

## Data Flow

1. **Market Data Ingestion** (Post-market close)
   - Angel One session authentication with TOTP
   - Incremental daily candle fetch
   - Derive weekly/monthly bars from daily data
   - Validate completeness and timestamps

2. **Data-Ready Validation**
   - Check for today's completed daily candle
   - Verify weekly/monthly bar completeness
   - Record data delays if validation fails

3. **Strategy Execution**
   - Load required data (daily, weekly, monthly, fundamentals)
   - Evaluate all conditions for each symbol
   - Rank candidates by strategy-specific criteria
   - Store detailed evaluation results

4. **Alert Delivery**
   - Deduplicate by strategy_version + signal_date + symbol
   - Format compact Telegram message
   - Attach CSV for lists > configured limit
   - Retry failed deliveries with exponential backoff

## API Endpoints

### Health & Status
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed system status

### Strategy Runs
- `GET /runs` - List all strategy runs
- `GET /runs/{run_id}` - Get specific run details

### Signals
- `GET /signals` - Query signals (filter by strategy, date, symbol)
- `GET /signals/{symbol}` - Get all signals for a symbol

### Strategies
- `GET /strategies` - List all strategies with definitions

### Admin
- `POST /admin/refresh-instruments` - Refresh instrument master
- `POST /admin/ingest-daily` - Trigger daily data ingestion
- `POST /admin/run-strategy/{strategy_name}` - Manual strategy run

## Strategy Definitions

### 1. VCP (Volatility Contraction Pattern)

**Schedule**: Daily EOD after data-ready validation

**Conditions**:
- ATR(14)[today] < ATR(14)[10 days ago]
- ATR(14)[today] / close[today] < 0.08
- close[today] > 0.75 × max(weekly close over last 52 completed weeks)
- EMA50 > EMA150 > EMA200
- close > EMA50
- close > ₹10
- close × volume > ₹1,000,000

**Output**: Labeled as "VCP candidate" (not BUY signal)

### 2. RB (Rocket Base)

**Schedule**: 
- Daily watchlist after data-ready validation
- Monthly confirmed after final monthly candle closes

**Conditions** (Chartink-compatible):
- daily WMA(close,1) > monthly WMA(close,2) + 1
- monthly WMA(close,2) > monthly WMA(close,4) + 2
- daily WMA(close,1) > weekly WMA(close,6) + 2
- weekly WMA(close,6) > weekly WMA(close,12) + 2
- daily WMA(close,1) > WMA(close,12)[4 days ago] + 2
- daily WMA(close,1) > WMA(close,20)[2 days ago] + 2
- ₹25 < close <= ₹500
- weekly volume > 85,000

**Output**: 
- Daily: "watchlist" candidates
- Month-end: "confirmed" candidates

### 3. Multi-bagger Technical

**Schedule**: Month-end after final monthly candle closes

**Conditions**:
- Completed monthly % change >= 20%
- Completed monthly RSI(14) >= 50
- Monthly EMA10 >= Monthly EMA20
- Daily EMA(volume, 30) >= 50,000
- close >= ₹20
- AND either:
  - At least one monthly EMA10 cross above EMA20 in last 20 completed months, OR
  - Completed monthly close crossed above monthly EMA10

**Output**: "Multi-bagger candidate"

### 4. Fundamental Stockexploder

**Schedule**: Month-end after fundamentals refresh

**Conditions**:
- Latest quarter EPS > Previous quarter EPS × 1.25
- Latest quarter sales > Previous quarter sales × 1.25
- Latest quarter EPS > Same quarter last year EPS
- Market cap < ₹5000 crores
- 1-month average volume > 50,000
- Price > ₹20
- RSI > 40
- Price > DMA200
- DMA50 > DMA200
- 3-year EPS growth > 20%

**Output**: "Fundamental Stockexploder candidate"

## Data Limitations

### Market Data
- **Source**: Angel One SmartAPI
- **Instruments**: NSE equity only
- **History**: Limited by Angel One API (typically 1-2 years)
- **Frequency**: Daily candles post-market close
- **Derived Data**: Weekly and monthly bars calculated locally

### Fundamentals Data
- **Provider Interface**: Pluggable architecture
- **Default**: Angel One (limited fundamental data)
- **Required Fields**: Quarterly EPS, quarterly sales, market cap, 3-year EPS growth
- **Limitations**: Angel One alone insufficient for complete fundamental analysis
- **Recommendation**: Integrate additional provider for comprehensive fundamentals

### Known Gaps
- Angel One does not provide quarterly sales data
- 3-year EPS growth calculation requires historical quarterly data
- Market cap may need external source for accuracy
- Restatements and filing dates not available from Angel One

## Alert Format

### Telegram Message Structure

```
🎯 VCP Candidates - 2024-01-15
Strategy Version: v1.0
Data Date: 2024-01-15 15:30 IST

Top 10 Candidates:
1. RELIANCE (₹2,450.50) ⭐⭐⭐⭐⭐
   ✓ ATR contracting
   ✓ Near 52W high
   ✓ EMA alignment
   
2. TCS (₹3,650.25) ⭐⭐⭐⭐
   ✓ ATR contracting
   ✓ EMA alignment
   ✗ Below 75% of 52W high

[Full list: 45 symbols - see attachment]

⚠️ SCREENING CANDIDATES ONLY - NOT BUY SIGNALS
📊 Data freshness: ✓ Current
```

### CSV Attachment (for lists > 10)

```csv
Symbol,Close,Rank,ATR_Contracting,Near_52W_High,EMA_Alignment,Volume_Filter,Data_Date
RELIANCE,2450.50,5,TRUE,TRUE,TRUE,TRUE,2024-01-15
TCS,3650.25,4,TRUE,FALSE,TRUE,TRUE,2024-01-15
...
```

## Testing

### Run All Tests
```bash
pytest tests/ -v --cov=app --cov-report=html
```

### Unit Tests
```bash
pytest tests/unit/ -v
```

### Integration Tests
```bash
pytest tests/integration/ -v
```

### Parity Tests
```bash
pytest tests/parity/ -v
```

Parity tests validate strategy outputs against manually exported Chartink/Screener.in results.

## Troubleshooting

### Angel One Authentication Failures

**Symptom**: "Invalid session" or "TOTP verification failed"

**Solutions**:
1. Verify TOTP secret is correct (base32 encoded)
2. Check system time synchronization (NTP)
3. Regenerate API credentials in Angel One portal
4. Review logs: `tail -f logs/angel_one.log`

### Missing Data

**Symptom**: "Data not ready" or "Incomplete candle"

**Solutions**:
1. Check Angel One API status
2. Verify NSE trading calendar (market holiday?)
3. Manual data refresh: `POST /admin/ingest-daily`
4. Review data ingestion logs: `tail -f logs/market_data.log`

### Telegram Delivery Failures

**Symptom**: Alerts not received

**Solutions**:
1. Verify bot token and chat ID
2. Check bot permissions in Telegram group
3. Review Telegram logs: `tail -f logs/telegram.log`
4. Test connection: `curl https://api.telegram.org/bot<TOKEN>/getMe`

### Database Connection Issues

**Symptom**: "Connection refused" or "Too many connections"

**Solutions**:
1. Check PostgreSQL service status
2. Verify DATABASE_URL in .env
3. Check connection pool settings
4. Review database logs

## Security Considerations

### Secrets Management
- All credentials via environment variables
- Never commit `.env` file
- Use secrets manager in production (Vault, AWS Secrets Manager)
- Rotate API keys regularly

### Logging
- API credentials redacted from all logs
- Telegram token masked in error messages
- PII (if any) not logged

### Network Security
- Rate limiting on API endpoints
- Angel One API rate limits respected
- Exponential backoff for retries
- No public exposure of admin endpoints

## Monitoring

### Key Metrics
- Data ingestion success rate
- Strategy execution time
- Alert delivery success rate
- API response times
- Database query performance

### Health Checks
- `/health/detailed` endpoint
- Database connectivity
- Angel One session status
- Telegram bot connectivity
- Scheduler job status

### Alerts
- Data ingestion failures
- Strategy execution errors
- Telegram delivery failures
- Database connection issues
- Disk space warnings

## Maintenance

### Daily
- Monitor data ingestion logs
- Verify alert delivery
- Check for failed jobs

### Weekly
- Review strategy performance
- Analyze candidate quality
- Check database size

### Monthly
- Update instrument master
- Review and rotate logs
- Database maintenance (VACUUM, ANALYZE)
- Backup database

### Quarterly
- Review and update strategy parameters
- Validate parity tests
- Update dependencies
- Security audit

## Roadmap

### Phase 1 (Current)
- ✅ Core infrastructure
- ✅ Angel One integration
- ✅ Four strategies implemented
- ✅ Telegram alerting
- ✅ Basic API

### Phase 2 (Planned)
- [ ] Additional fundamentals providers
- [ ] Web dashboard
- [ ] Backtesting framework
- [ ] Strategy parameter optimization
- [ ] Advanced filtering options

### Phase 3 (Future)
- [ ] Real-time intraday scanning
- [ ] Custom strategy builder
- [ ] Portfolio tracking
- [ ] Performance analytics

## Contributing

This is an alert-only system. Contributions that add trading/order functionality will be rejected.

### Guidelines
- Follow existing code structure
- Add tests for new features
- Update documentation
- Maintain security standards
- No auto-trading code

## License

MIT License - See LICENSE file

## Disclaimer

**THIS SOFTWARE IS FOR EDUCATIONAL AND INFORMATIONAL PURPOSES ONLY.**

- Not financial advice
- No guarantee of accuracy
- Past performance ≠ future results
- Consult a financial advisor before trading
- Use at your own risk

**NO AUTO-TRADING**: This system only generates alerts. It never places, modifies, or cancels orders.

## Support

- Documentation: `docs/`
- Issues: GitHub Issues
- Runbook: `docs/RUNBOOK.md`

## Acknowledgments

- Strategy definitions based on publicly available screening criteria
- Angel One SmartAPI for market data
- Telegram for alert delivery
</content>
</write_to_file>

Now let me create the project structure and core files:

<execute_command>
<command>cd /Users/nishantprajapati/BOB-Projects/nse-strategy-alerts && mkdir -p app/{api,core,market_data,fundamentals,strategies,scheduler,telegram,models} tests/{unit,integration,parity} alembic/versions docs deployment logs</command>
<timeout>10</timeout>
<background>false</background>
</execute_command>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/.env.example</file_path>
<content># Database Configuration
DATABASE_URL=postgresql+asyncpg://nse_user:nse_password@localhost:5432/nse_alerts
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Angel One API Configuration
ANGEL_API_KEY=your_api_key_here
ANGEL_CLIENT_ID=your_client_id_here
ANGEL_PASSWORD=your_password_here
ANGEL_TOTP_SECRET=your_totp_secret_base32_here
ANGEL_API_TIMEOUT=30
ANGEL_MAX_RETRIES=3
ANGEL_RATE_LIMIT_CALLS=10
ANGEL_RATE_LIMIT_PERIOD=1

# Fundamentals Provider Configuration
# Options: 'angel_one', 'mock'
FUNDAMENTALS_PROVIDER=mock
FUNDAMENTALS_API_KEY=
FUNDAMENTALS_API_TIMEOUT=30

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_MAX_MESSAGE_LENGTH=4096
TELEGRAM_MAX_SYMBOLS_IN_MESSAGE=10
TELEGRAM_RETRY_ATTEMPTS=3
TELEGRAM_RETRY_DELAY=5

# Scheduler Configuration
SCHEDULER_TIMEZONE=Asia/Kolkata
ENABLE_SCHEDULER=true
DATA_READY_CHECK_TIME=15:45
VCP_SCAN_TIME=16:00
RB_DAILY_SCAN_TIME=16:05
MONTHLY_SCAN_TIME=16:10
DATA_INGESTION_TIME=15:35

# Application Configuration
APP_NAME=NSE Strategy Alerts
APP_VERSION=1.0.0
DEBUG=false
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# Security
SECRET_KEY=your_secret_key_here_min_32_chars
API_KEY_HEADER=X-API-Key
ADMIN_API_KEY=your_admin_api_key_here

# Data Validation
MAX_DATA_DELAY_HOURS=24
MIN_DAILY_VOLUME=10000
MIN_PRICE=1.0
MAX_PRICE=100000

# Strategy Configuration
VCP_MIN_RANK=3
RB_MIN_RANK=3
MULTIBAGGER_MIN_RANK=3
FUNDAMENTAL_MIN_RANK=3

# Cache Configuration
CACHE_INSTRUMENTS_TTL=86400
CACHE_CANDLES_TTL=3600

# Performance
MAX_WORKERS=4
BATCH_SIZE=100
QUERY_TIMEOUT=30

# Feature Flags
ENABLE_VCP_STRATEGY=true
ENABLE_RB_STRATEGY=true
ENABLE_MULTIBAGGER_STRATEGY=true
ENABLE_FUNDAMENTAL_STRATEGY=true
ENABLE_PARITY_TESTING=false
</content>
</write_to_file>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/.gitignore</file_path>
<content># Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/
env/

# Environment Variables
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Testing
.pytest_cache/
.coverage
htmlcov/
*.cover
.hypothesis/

# Logs
logs/*.log
*.log

# Database
*.db
*.sqlite
*.sqlite3

# Alembic
alembic.ini

# Jupyter
.ipynb_checkpoints/
*.ipynb

# Cache
.cache/
*.cache

# Temporary files
tmp/
temp/
*.tmp

# Podman/Docker
.env.production
docker-compose.override.yml

# Data files
data/*.csv
data/*.json
data/*.parquet
!data/.gitkeep

# Backup files
*.bak
*.backup

# OS
Thumbs.db
.DS_Store

# Secrets
secrets/
*.pem
*.key
*.crt

# Reports
reports/*.html
reports/*.pdf
!reports/.gitkeep
</content>
</write_to_file>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/requirements.txt</file_path>
<content># Core Framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0

# Database
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
alembic==1.13.1
psycopg2-binary==2.9.9

# Scheduling
apscheduler==3.10.4
pytz==2024.1

# HTTP Client
httpx==0.26.0
aiohttp==3.9.1

# Data Processing
pandas==2.2.0
numpy==1.26.3
ta-lib==0.4.28

# Angel One API
smartapi-python==1.3.0
pyotp==2.9.0

# Telegram
python-telegram-bot==20.7

# Utilities
python-dateutil==2.8.2
python-dotenv==1.0.0
tenacity==8.2.3

# Logging
structlog==24.1.0
python-json-logger==2.0.7

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0
pytest-mock==3.12.0
httpx-mock==0.7.0
faker==22.0.0

# Development
black==24.1.1
flake8==7.0.0
mypy==1.8.0
isort==5.13.2
pre-commit==3.6.0

# Documentation
mkdocs==1.5.3
mkdocs-material==9.5.6

# Security
cryptography==42.0.0
</content>
</write_to_file>

Now let me create the core application structure:

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/app/__init__.py</file_path>
<content>"""NSE Strategy Alerts - Alert-Only Stock Screening System."""

__version__ = "1.0.0"
__author__ = "NSE Strategy Alerts Team"
__description__ = "Alert-only NSE stock screening system - No auto-trading"
</content>
</write_to_file>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/app/core/config.py</file_path>
<content>"""Application configuration management."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="NSE Strategy Alerts")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/app.log")
    log_max_bytes: int = Field(default=10485760)  # 10MB
    log_backup_count: int = Field(default=5)

    # Database
    database_url: str = Field(
        ..., description="PostgreSQL connection URL with asyncpg driver"
    )
    database_pool_size: int = Field(default=20)
    database_max_overflow: int = Field(default=10)

    # Angel One API
    angel_api_key: str = Field(..., description="Angel One API key")
    angel_client_id: str = Field(..., description="Angel One client ID")
    angel_password: str = Field(..., description="Angel One password")
    angel_totp_secret: str = Field(..., description="Angel One TOTP secret (base32)")
    angel_api_timeout: int = Field(default=30)
    angel_max_retries: int = Field(default=3)
    angel_rate_limit_calls: int = Field(default=10)
    angel_rate_limit_period: int = Field(default=1)

    # Fundamentals Provider
    fundamentals_provider: str = Field(
        default="mock", description="Fundamentals data provider: 'angel_one' or 'mock'"
    )
    fundamentals_api_key: Optional[str] = Field(default=None)
    fundamentals_api_timeout: int = Field(default=30)

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram bot token")
    telegram_chat_id: str = Field(..., description="Telegram chat/channel ID")
    telegram_max_message_length: int = Field(default=4096)
    telegram_max_symbols_in_message: int = Field(default=10)
    telegram_retry_attempts: int = Field(default=3)
    telegram_retry_delay: int = Field(default=5)

    # Scheduler
    scheduler_timezone: str = Field(default="Asia/Kolkata")
    enable_scheduler: bool = Field(default=True)
    data_ready_check_time: str = Field(default="15:45")
    vcp_scan_time: str = Field(default="16:00")
    rb_daily_scan_time: str = Field(default="16:05")
    monthly_scan_time: str = Field(default="16:10")
    data_ingestion_time: str = Field(default="15:35")

    # Security
    secret_key: str = Field(..., min_length=32, description="Secret key for signing")
    api_key_header: str = Field(default="X-API-Key")
    admin_api_key: str = Field(..., description="Admin API key")

    # Data Validation
    max_data_delay_hours: int = Field(default=24)
    min_daily_volume: int = Field(default=10000)
    min_price: float = Field(default=1.0)
    max_price: float = Field(default=100000.0)

    # Strategy Configuration
    vcp_min_rank: int = Field(default=3)
    rb_min_rank: int = Field(default=3)
    multibagger_min_rank: int = Field(default=3)
    fundamental_min_rank: int = Field(default=3)

    # Cache Configuration
    cache_instruments_ttl: int = Field(default=86400)  # 24 hours
    cache_candles_ttl: int = Field(default=3600)  # 1 hour

    # Performance
    max_workers: int = Field(default=4)
    batch_size: int = Field(default=100)
    query_timeout: int = Field(default=30)

    # Feature Flags
    enable_vcp_strategy: bool = Field(default=True)
    enable_rb_strategy: bool = Field(default=True)
    enable_multibagger_strategy: bool = Field(default=True)
    enable_fundamental_strategy: bool = Field(default=True)
    enable_parity_testing: bool = Field(default=False)

    @field_validator("fundamentals_provider")
    @classmethod
    def validate_fundamentals_provider(cls, v: str) -> str:
        """Validate fundamentals provider value."""
        allowed = ["angel_one", "mock"]
        if v not in allowed:
            raise ValueError(f"fundamentals_provider must be one of {allowed}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level value."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v_upper

    def get_redacted_config(self) -> dict:
        """Get configuration with sensitive values redacted."""
        config = self.model_dump()
        sensitive_keys = [
            "angel_api_key",
            "angel_password",
            "angel_totp_secret",
            "telegram_bot_token",
            "secret_key",
            "admin_api_key",
            "fundamentals_api_key",
            "database_url",
        ]
        for key in sensitive_keys:
            if key in config and config[key]:
                config[key] = "***REDACTED***"
        return config


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
</content>
</write_to_file>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/app/core/database.py</file_path>
<content>"""Database connection and session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# SQLAlchemy Base
Base = declarative_base()

# Global engine and session factory
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            poolclass=NullPool if settings.debug else None,
        )
        logger.info("Database engine created", database_url=settings.database_url.split("@")[-1])
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        logger.info("Session factory created")
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get database session.
    
    Usage:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session.
    
    Usage:
        async with get_db_context() as db:
            result = await db.execute(query)
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database (create tables if they don't exist)."""
    engine = get_engine()
    async with engine.begin() as conn:
        # Import all models to ensure they're registered
        from app.models import (  # noqa: F401
            candle,
            fundamental,
            instrument,
            signal,
            strategy_run,
            telegram_alert,
        )
        
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")


async def close_db() -> None:
    """Close database connections."""
    global _engine, _async_session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connections closed")


async def check_db_connection() -> bool:
    """Check if database connection is healthy."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("Database connection check failed", error=str(e))
        return False
</content>
</write_to_file>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/app/core/logging.py</file_path>
<content>"""Structured logging configuration with sensitive data redaction."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def redact_sensitive_data(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Redact sensitive data from log events."""
    sensitive_keys = {
        "password",
        "api_key",
        "token",
        "secret",
        "totp",
        "authorization",
        "auth",
        "credential",
    }
    
    def redact_dict(d: dict) -> dict:
        """Recursively redact sensitive keys in dictionary."""
        redacted = {}
        for key, value in d.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = redact_dict(value)
            elif isinstance(value, (list, tuple)):
                redacted[key] = [
                    redact_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted
    
    return redact_dict(event_dict)


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add application context to log events."""
    event_dict["app"] = settings.app_name
    event_dict["version"] = settings.app_version
    return event_dict


def configure_logging() -> None:
    """Configure structured logging with file and console handlers."""
    # Ensure log directory exists
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.handlers.RotatingFileHandler(
                settings.log_file,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
            ),
        ],
    )
    
    # Configure structlog
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        add_app_context,
        redact_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if settings.debug:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Configure logging on module import
configure_logging()
</content>
</write_to_file>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/app/core/security.py</file_path>
<content>"""Security utilities for API authentication and authorization."""

from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# API Key header scheme
api_key_header = APIKeyHeader(name=settings.api_key_header, auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Verify API key from request header.
    
    Args:
        api_key: API key from request header
        
    Returns:
        Verified API key
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        logger.warning("API key missing from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={settings.api_key_header: "Required"},
        )
    
    # In production, validate against database or secrets manager
    # For now, validate against admin API key
    if api_key != settings.admin_api_key:
        logger.warning("Invalid API key provided", api_key_prefix=api_key[:8])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    
    return api_key


async def verify_admin_api_key(api_key: str = Security(verify_api_key)) -> str:
    """
    Verify admin API key for privileged operations.
    
    Args:
        api_key: Verified API key
        
    Returns:
        Verified admin API key
        
    Raises:
        HTTPException: If API key is not admin key
    """
    if api_key != settings.admin_api_key:
        logger.warning("Non-admin API key used for admin endpoint")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    
    return api_key


def mask_sensitive_value(value: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive value for logging.
    
    Args:
        value: Sensitive value to mask
        visible_chars: Number of characters to show at start
        
    Returns:
        Masked value
    """
    if not value or len(value) <= visible_chars:
        return "***"
    return f"{value[:visible_chars]}***"
</content>
</write_to_file>

Now let me create the database models:

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/app/models/__init__.py</file_path>
<content>"""Database models for NSE Strategy Alerts."""

from app.models.candle import DailyCandle, MonthlyCandle, WeeklyCandle
from app.models.fundamental import FundamentalData
from app.models.instrument import Instrument
from app.models.signal import Signal, SignalCondition
from app.models.strategy_run import StrategyRun
from app.models.telegram_alert import TelegramAlert

__all__ = [
    "Instrument",
    "DailyCandle",
    "WeeklyCandle",
    "MonthlyCandle",
    "FundamentalData",
    "StrategyRun",
    "Signal",
    "SignalCondition",
    "TelegramAlert",
]
</content>
</write_to_file>

<write_to_file>
<file_path>/Users/nishantprajapati/BOB-Projects/nse-strategy-alerts/app/models/instrument.py</file_path>
<content>"""Instrument master model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Instrument(Base):
    """NSE instrument master data."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Angel One identifiers
    token: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    
    # Instrument details
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, default="NSE")
    instrument_type: Mapped[str] = mapped_column(String(20), nullable=False)
    isin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Trading info
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tick_size: Mapped[float] = mapped_column(nullable=False, default=0.05)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Metadata
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_symbol_exchange", "symbol", "exchange"),
        Index("idx_active_instruments", "is_active", "exchange"),
    )

    def __repr__(self) -> str:
        return f"<Instrument(symbol={self.symbol}, token={self.token}, exchange={self.exchange})>"
