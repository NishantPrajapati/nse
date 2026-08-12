# NSE Strategy Alerts Runbook

## Table of Contents
1. [Common Operations](#common-operations)
2. [Troubleshooting](#troubleshooting)
3. [Monitoring](#monitoring)
4. [Maintenance](#maintenance)
5. [Emergency Procedures](#emergency-procedures)

## Common Operations

### Starting the Application

#### Development Mode
```bash
# Activate virtual environment
source venv/bin/activate

# Run database migrations
alembic upgrade head

# Start application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Production Mode (Podman Compose)
```bash
cd deployment

# Start all services
podman-compose up -d

# View logs
podman-compose logs -f app

# Check status
podman-compose ps
```

### Stopping the Application

```bash
# Development
Ctrl+C

# Production
cd deployment
podman-compose down
```

### Restarting Services

```bash
# Restart application only
podman-compose restart app

# Restart all services
podman-compose restart

# Restart with rebuild
podman-compose up -d --build
```

## Troubleshooting

### Angel One Authentication Failures

**Symptom**: "Invalid session" or "TOTP verification failed" errors in logs

**Diagnosis**:
```bash
# Check Angel One credentials in logs
grep "Angel One" logs/app.log | tail -20

# Verify TOTP secret
python3 -c "import pyotp; print(pyotp.TOTP('YOUR_TOTP_SECRET').now())"
```

**Solutions**:

1. **Verify TOTP Secret**:
   - Ensure TOTP secret is base32 encoded
   - Check system time is synchronized (NTP)
   - Test TOTP generation manually

2. **Regenerate API Credentials**:
   - Log into Angel One portal
   - Navigate to API section
   - Generate new API key and secret
   - Update `.env` file
   - Restart application

3. **Check Rate Limits**:
   ```bash
   # Check for rate limit errors
   grep "rate limit" logs/app.log
   ```
   - Adjust `ANGEL_RATE_LIMIT_CALLS` and `ANGEL_RATE_LIMIT_PERIOD` in `.env`

4. **Session Expiry**:
   - Angel One sessions last ~24 hours
   - Application auto-refreshes sessions
   - Check `session_expiry` in logs

### Missing or Incomplete Data

**Symptom**: "Data not ready" or "Incomplete candle" warnings

**Diagnosis**:
```bash
# Check data ingestion logs
grep "data ingestion" logs/app.log | tail -50

# Check data validation
grep "data validation" logs/app.log | tail -20

# Query database for latest data
psql -U nse_user -d nse_alerts -c "SELECT MAX(date) FROM daily_candles;"
```

**Solutions**:

1. **Manual Data Refresh**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/admin/ingest-daily \
     -H "X-API-Key: YOUR_ADMIN_API_KEY"
   ```

2. **Check NSE Trading Calendar**:
   - Verify today is a trading day
   - Check for unscheduled market holidays
   - Update `nse_calendar.py` if needed

3. **Angel One API Issues**:
   ```bash
   # Test Angel One connectivity
   curl -X GET http://localhost:8000/api/v1/health/detailed \
     -H "X-API-Key: YOUR_API_KEY"
   ```

4. **Database Issues**:
   ```bash
   # Check database connectivity
   podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "SELECT 1;"
   
   # Check table sizes
   podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "
   SELECT 
     schemaname,
     tablename,
     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
   FROM pg_tables
   WHERE schemaname = 'public'
   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
   "
   ```

### Telegram Delivery Failures

**Symptom**: Alerts not received in Telegram

**Diagnosis**:
```bash
# Check Telegram logs
grep "Telegram" logs/app.log | tail -50

# Check failed alerts
psql -U nse_user -d nse_alerts -c "
SELECT id, strategy_name, status, error_message, attempt_count 
FROM telegram_alerts 
WHERE status IN ('failed', 'retrying') 
ORDER BY created_at DESC 
LIMIT 10;
"
```

**Solutions**:

1. **Verify Bot Token and Chat ID**:
   ```bash
   # Test bot connection
   curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe
   
   # Get chat ID
   curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```

2. **Check Bot Permissions**:
   - Ensure bot is added to channel/group
   - Verify bot has permission to send messages
   - Check if bot is admin (if required)

3. **Manual Retry**:
   ```bash
   # Retry failed alerts via API
   # (Automatic retry runs every 5 minutes)
   ```

4. **Network Issues**:
   ```bash
   # Test Telegram API connectivity
   curl -I https://api.telegram.org
   
   # Check firewall rules
   # Ensure outbound HTTPS (443) is allowed
   ```

### Database Connection Issues

**Symptom**: "Connection refused" or "Too many connections"

**Diagnosis**:
```bash
# Check database status
podman exec -it nse-alerts-db pg_isready -U nse_user

# Check active connections
podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "
SELECT count(*) as connections, state 
FROM pg_stat_activity 
WHERE datname = 'nse_alerts' 
GROUP BY state;
"

# Check connection pool settings
grep "DATABASE_POOL" .env
```

**Solutions**:

1. **Restart Database**:
   ```bash
   podman-compose restart postgres
   ```

2. **Adjust Connection Pool**:
   - Edit `.env`:
     ```
     DATABASE_POOL_SIZE=20
     DATABASE_MAX_OVERFLOW=10
     ```
   - Restart application

3. **Kill Idle Connections**:
   ```bash
   podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "
   SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE datname = 'nse_alerts' 
     AND state = 'idle' 
     AND state_change < now() - interval '1 hour';
   "
   ```

### Strategy Execution Failures

**Symptom**: Strategy runs marked as "failed" in database

**Diagnosis**:
```bash
# Check recent strategy runs
psql -U nse_user -d nse_alerts -c "
SELECT id, strategy_name, status, error_message, started_at 
FROM strategy_runs 
WHERE status = 'failed' 
ORDER BY started_at DESC 
LIMIT 10;
"

# Check strategy logs
grep "strategy run" logs/app.log | tail -100
```

**Solutions**:

1. **Review Error Message**:
   - Check `error_message` field in `strategy_runs` table
   - Look for specific error patterns

2. **Manual Strategy Run**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/admin/run-strategy/VCP \
     -H "X-API-Key: YOUR_ADMIN_API_KEY"
   ```

3. **Check Data Availability**:
   - Ensure sufficient historical data exists
   - Verify data completeness flags

4. **Disable Problematic Strategy**:
   - Edit `.env`:
     ```
     ENABLE_VCP_STRATEGY=false
     ```
   - Restart application

## Monitoring

### Health Checks

```bash
# Basic health check
curl http://localhost:8000/health

# Detailed health check
curl http://localhost:8000/api/v1/health/detailed \
  -H "X-API-Key: YOUR_API_KEY" | jq
```

### Key Metrics to Monitor

1. **Data Freshness**:
   ```sql
   SELECT MAX(date) as latest_date, COUNT(*) as symbols
   FROM daily_candles
   WHERE is_complete = true;
   ```

2. **Strategy Success Rate**:
   ```sql
   SELECT 
     strategy_name,
     COUNT(*) as total_runs,
     SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful,
     AVG(duration_seconds) as avg_duration
   FROM strategy_runs
   WHERE started_at > NOW() - INTERVAL '7 days'
   GROUP BY strategy_name;
   ```

3. **Alert Delivery Rate**:
   ```sql
   SELECT 
     status,
     COUNT(*) as count,
     AVG(attempt_count) as avg_attempts
   FROM telegram_alerts
   WHERE created_at > NOW() - INTERVAL '7 days'
   GROUP BY status;
   ```

4. **Database Size**:
   ```bash
   podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "
   SELECT pg_size_pretty(pg_database_size('nse_alerts'));
   "
   ```

### Log Monitoring

```bash
# Follow application logs
tail -f logs/app.log

# Search for errors
grep "ERROR" logs/app.log | tail -50

# Search for specific strategy
grep "VCP" logs/app.log | tail -100

# Monitor scheduler jobs
grep "scheduler" logs/app.log | tail -50
```

## Maintenance

### Daily Maintenance

1. **Check Data Ingestion**:
   - Verify daily candles ingested
   - Check for data delays
   - Review ingestion logs

2. **Monitor Alert Delivery**:
   - Verify alerts sent successfully
   - Check for failed deliveries
   - Review retry queue

3. **Review Strategy Runs**:
   - Check completion status
   - Review candidate counts
   - Verify data quality

### Weekly Maintenance

1. **Database Maintenance**:
   ```bash
   # Vacuum and analyze
   podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "
   VACUUM ANALYZE;
   "
   
   # Check for bloat
   podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "
   SELECT 
     schemaname,
     tablename,
     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
   FROM pg_tables
   WHERE schemaname = 'public'
   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
   "
   ```

2. **Log Rotation**:
   ```bash
   # Archive old logs
   cd logs
   tar -czf app-$(date +%Y%m%d).tar.gz app.log
   > app.log  # Truncate current log
   ```

3. **Backup Database**:
   ```bash
   # Create backup
   podman exec -it nse-alerts-db pg_dump -U nse_user nse_alerts > backup-$(date +%Y%m%d).sql
   
   # Compress backup
   gzip backup-$(date +%Y%m%d).sql
   ```

### Monthly Maintenance

1. **Update Instrument Master**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/admin/refresh-instruments?force=true \
     -H "X-API-Key: YOUR_ADMIN_API_KEY"
   ```

2. **Clean Old Data**:
   ```sql
   -- Delete candles older than 2 years
   DELETE FROM daily_candles WHERE date < NOW() - INTERVAL '2 years';
   DELETE FROM weekly_candles WHERE week_start_date < NOW() - INTERVAL '2 years';
   DELETE FROM monthly_candles WHERE month_start_date < NOW() - INTERVAL '2 years';
   
   -- Vacuum after deletion
   VACUUM ANALYZE;
   ```

3. **Update Dependencies**:
   ```bash
   # Check for updates
   pip list --outdated
   
   # Update (test in dev first)
   pip install --upgrade -r requirements.txt
   ```

4. **Review and Update NSE Calendar**:
   - Check NSE website for upcoming holidays
   - Update `app/scheduler/nse_calendar.py`
   - Restart application

### Quarterly Maintenance

1. **Security Audit**:
   - Rotate API keys
   - Review access logs
   - Update secrets

2. **Performance Review**:
   - Analyze query performance
   - Review database indexes
   - Optimize slow queries

3. **Strategy Review**:
   - Analyze strategy performance
   - Review parameter settings
   - Update strategy versions if needed

## Emergency Procedures

### Complete System Failure

1. **Stop All Services**:
   ```bash
   cd deployment
   podman-compose down
   ```

2. **Check System Resources**:
   ```bash
   df -h  # Disk space
   free -h  # Memory
   top  # CPU usage
   ```

3. **Review Logs**:
   ```bash
   tail -100 logs/app.log
   journalctl -u podman-compose -n 100
   ```

4. **Restore from Backup** (if needed):
   ```bash
   # Restore database
   gunzip -c backup-YYYYMMDD.sql.gz | \
     podman exec -i nse-alerts-db psql -U nse_user nse_alerts
   ```

5. **Restart Services**:
   ```bash
   podman-compose up -d
   ```

### Data Corruption

1. **Identify Affected Tables**:
   ```sql
   -- Check for inconsistencies
   SELECT COUNT(*) FROM daily_candles WHERE close < 0;
   SELECT COUNT(*) FROM signals WHERE conditions_passed > conditions_total;
   ```

2. **Backup Current State**:
   ```bash
   podman exec -it nse-alerts-db pg_dump -U nse_user nse_alerts > emergency-backup.sql
   ```

3. **Clean Corrupted Data**:
   ```sql
   -- Delete invalid records
   DELETE FROM daily_candles WHERE close < 0 OR high < low;
   ```

4. **Re-ingest Data**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/admin/ingest-daily \
     -H "X-API-Key: YOUR_ADMIN_API_KEY"
   ```

### Security Breach

1. **Immediate Actions**:
   - Stop application: `podman-compose down`
   - Rotate all API keys and secrets
   - Review access logs
   - Change database passwords

2. **Investigation**:
   ```bash
   # Check for unauthorized access
   grep "401\|403" logs/app.log
   
   # Review database connections
   podman exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "
   SELECT * FROM pg_stat_activity;
   "
   ```

3. **Recovery**:
   - Update all credentials in `.env`
   - Restart with new secrets
   - Monitor for suspicious activity

## Contact Information

- **Application Owner**: [Your Name]
- **Email**: [your.email@company.com]
- **On-Call**: [On-call rotation details]
- **Escalation**: [Manager/Team Lead contact]

## Additional Resources

- [README.md](../README.md) - Setup and usage guide
- [API Documentation](http://localhost:8000/docs) - Interactive API docs
- [Angel One API Docs](https://smartapi.angelbroking.com/docs)
- [Telegram Bot API](https://core.telegram.org/bots/api)
