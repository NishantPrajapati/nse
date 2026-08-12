# VPS Deployment Guide for NSE Strategy Alerts

## Prerequisites

- VPS with Ubuntu 22.04 LTS or later
- Minimum 2GB RAM, 2 CPU cores, 20GB storage
- Root or sudo access
- Domain name (optional, for HTTPS)

## Step 1: Initial VPS Setup

### Connect to VPS
```bash
ssh root@your-vps-ip
# or
ssh your-user@your-vps-ip
```

### Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### Install Required Packages
```bash
# Install Docker and Docker Compose
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group (if not root)
sudo usermod -aG docker $USER
newgrp docker

# Install Git
sudo apt install -y git

# Install Python (for local testing if needed)
sudo apt install -y python3.12 python3.12-venv python3-pip
```

## Step 2: Clone Repository

```bash
# Create application directory
sudo mkdir -p /opt/nse-alerts
sudo chown $USER:$USER /opt/nse-alerts
cd /opt/nse-alerts

# Clone repository
git clone git@github.com:NishantPrajapati/nse-strategy-alerts.git .
# or if using HTTPS:
# git clone https://github.com/NishantPrajapati/nse-strategy-alerts.git .
```

## Step 3: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit environment file
nano .env
```

### Required Environment Variables

```bash
# Database (use strong password)
DATABASE_URL=postgresql+asyncpg://nse_user:STRONG_PASSWORD_HERE@postgres:5432/nse_alerts

# Angel One API (from your Angel One account)
ANGEL_API_KEY=your_api_key_here
ANGEL_CLIENT_ID=your_client_id_here
ANGEL_PASSWORD=your_password_here
ANGEL_TOTP_SECRET=your_totp_secret_base32_here

# Telegram (from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Security (generate strong random keys)
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_API_KEY=$(openssl rand -hex 32)

# Application
DEBUG=false
LOG_LEVEL=INFO
ENABLE_SCHEDULER=true
```

### Generate Secure Keys
```bash
# Generate SECRET_KEY
openssl rand -hex 32

# Generate ADMIN_API_KEY
openssl rand -hex 32
```

## Step 4: Setup Docker Compose

### Create Production Docker Compose Override
```bash
cat > docker-compose.override.yml << 'EOF'
version: '3.8'

services:
  postgres:
    restart: always
    volumes:
      - /opt/nse-alerts/data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  app:
    restart: always
    volumes:
      - /opt/nse-alerts/logs:/app/logs
      - /opt/nse-alerts/data:/app/data
    environment:
      DATABASE_URL: postgresql+asyncpg://nse_user:${DB_PASSWORD}@postgres:5432/nse_alerts
EOF
```

### Create Data Directories
```bash
mkdir -p /opt/nse-alerts/data/postgres
mkdir -p /opt/nse-alerts/logs
chmod 755 /opt/nse-alerts/data
chmod 755 /opt/nse-alerts/logs
```

## Step 5: Deploy Application

### Build and Start Services
```bash
cd /opt/nse-alerts/deployment

# Build images
docker compose build

# Start services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f app
```

### Verify Deployment
```bash
# Check health endpoint
curl http://localhost:8000/health

# Check detailed health (replace with your ADMIN_API_KEY)
curl -H "X-API-Key: YOUR_ADMIN_API_KEY" http://localhost:8000/api/v1/health/detailed
```

## Step 6: Setup Firewall

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (if using reverse proxy)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow application port (if exposing directly)
sudo ufw allow 8000/tcp

# Enable firewall
sudo ufw enable
```

## Step 7: Setup Reverse Proxy (Optional but Recommended)

### Install Nginx
```bash
sudo apt install -y nginx
```

### Configure Nginx
```bash
sudo nano /etc/nginx/sites-available/nse-alerts
```

Add configuration:
```nginx
server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/nse-alerts /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Setup SSL with Let's Encrypt (Recommended)
```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```

## Step 8: Setup Monitoring

### Create Systemd Service for Auto-restart
```bash
sudo nano /etc/systemd/system/nse-alerts.service
```

Add:
```ini
[Unit]
Description=NSE Strategy Alerts
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/nse-alerts/deployment
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable nse-alerts
sudo systemctl start nse-alerts
```

### Setup Log Rotation
```bash
sudo nano /etc/logrotate.d/nse-alerts
```

Add:
```
/opt/nse-alerts/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 root root
    sharedscripts
    postrotate
        docker compose -f /opt/nse-alerts/deployment/docker-compose.yml restart app > /dev/null 2>&1 || true
    endscript
}
```

## Step 9: Setup Automated Backups

### Create Backup Script
```bash
sudo nano /opt/nse-alerts/backup.sh
```

Add:
```bash
#!/bin/bash
BACKUP_DIR="/opt/nse-alerts/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
docker exec nse-alerts-db pg_dump -U nse_user nse_alerts | gzip > $BACKUP_DIR/db_backup_$DATE.sql.gz

# Backup environment file
cp /opt/nse-alerts/.env $BACKUP_DIR/env_backup_$DATE

# Keep only last 7 days of backups
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "env_backup_*" -mtime +7 -delete

echo "Backup completed: $DATE"
```

Make executable:
```bash
chmod +x /opt/nse-alerts/backup.sh
```

### Setup Cron Job for Daily Backups
```bash
crontab -e
```

Add:
```
# Daily backup at 2 AM
0 2 * * * /opt/nse-alerts/backup.sh >> /opt/nse-alerts/logs/backup.log 2>&1
```

## Step 10: Monitoring and Maintenance

### View Logs
```bash
# Application logs
docker compose logs -f app

# Database logs
docker compose logs -f postgres

# System logs
tail -f /opt/nse-alerts/logs/app.log
```

### Check Resource Usage
```bash
# Docker stats
docker stats

# System resources
htop
df -h
free -h
```

### Update Application
```bash
cd /opt/nse-alerts

# Pull latest changes
git pull origin main

# Rebuild and restart
cd deployment
docker compose down
docker compose build
docker compose up -d

# Check logs
docker compose logs -f app
```

## Troubleshooting

### Application Won't Start
```bash
# Check logs
docker compose logs app

# Check environment variables
docker compose config

# Verify database connection
docker exec -it nse-alerts-db psql -U nse_user -d nse_alerts -c "SELECT 1;"
```

### Database Connection Issues
```bash
# Restart database
docker compose restart postgres

# Check database logs
docker compose logs postgres

# Verify credentials in .env file
```

### High Memory Usage
```bash
# Check container stats
docker stats

# Restart application
docker compose restart app

# Adjust memory limits in docker-compose.yml if needed
```

## Security Best Practices

1. **Use Strong Passwords**: Generate random passwords for database and API keys
2. **Enable Firewall**: Only allow necessary ports
3. **Setup SSL**: Use Let's Encrypt for HTTPS
4. **Regular Updates**: Keep system and Docker images updated
5. **Monitor Logs**: Check logs regularly for suspicious activity
6. **Backup Regularly**: Automate database backups
7. **Restrict SSH**: Use SSH keys instead of passwords
8. **Use Non-Root User**: Run application as non-root user

## Performance Optimization

### Adjust Docker Resources
Edit `docker-compose.yml`:
```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Database Tuning
```bash
# Connect to database
docker exec -it nse-alerts-db psql -U nse_user nse_alerts

# Optimize queries
VACUUM ANALYZE;

# Check slow queries
SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;
```

## Monitoring Setup (Optional)

### Install Prometheus and Grafana
```bash
# Add monitoring services to docker-compose.yml
# See monitoring/docker-compose.monitoring.yml for example
```

## Support

- **Documentation**: See README.md and RUNBOOK.md
- **Logs**: Check `/opt/nse-alerts/logs/`
- **Health Check**: `curl http://localhost:8000/health`
- **API Docs**: `http://your-domain.com/docs`

## Quick Reference Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# Restart services
docker compose restart

# View logs
docker compose logs -f

# Update application
git pull && docker compose up -d --build

# Backup database
docker exec nse-alerts-db pg_dump -U nse_user nse_alerts > backup.sql

# Restore database
cat backup.sql | docker exec -i nse-alerts-db psql -U nse_user nse_alerts
```
