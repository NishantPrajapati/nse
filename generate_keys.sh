#!/bin/bash

# Generate secure random keys for NSE Strategy Alerts

echo "🔐 Generating Secure Keys for NSE Strategy Alerts"
echo "=================================================="
echo ""

# Generate SECRET_KEY
SECRET_KEY=$(openssl rand -hex 32)
echo "SECRET_KEY=$SECRET_KEY"
echo ""

# Generate ADMIN_API_KEY
ADMIN_API_KEY=$(openssl rand -hex 32)
echo "ADMIN_API_KEY=$ADMIN_API_KEY"
echo ""

# Generate DB_PASSWORD
DB_PASSWORD=$(openssl rand -hex 16)
echo "DB_PASSWORD=$DB_PASSWORD"
echo ""

echo "=================================================="
echo "✅ Keys generated successfully!"
echo ""
echo "📝 Add these to your .env file:"
echo ""
echo "SECRET_KEY=$SECRET_KEY"
echo "ADMIN_API_KEY=$ADMIN_API_KEY"
echo "DB_PASSWORD=$DB_PASSWORD"
echo ""
echo "🔒 Keep these keys secure and never commit them to git!"
