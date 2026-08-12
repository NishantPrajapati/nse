#!/bin/bash

# NSE Strategy Alerts - GitHub Setup Script
# This script creates a new GitHub repository and pushes the code

set -e

echo "🚀 NSE Strategy Alerts - GitHub Setup"
echo "======================================"
echo ""

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed."
    echo "Install it from: https://cli.github.com/"
    echo ""
    echo "Or use manual setup:"
    echo "1. Create repository on GitHub: https://github.com/new"
    echo "2. Repository name: nse-strategy-alerts"
    echo "3. Make it private (recommended for trading strategies)"
    echo "4. Run these commands:"
    echo ""
    echo "   git remote add origin git@github.com:NishantPrajapati/nse-strategy-alerts.git"
    echo "   git branch -M main"
    echo "   git push -u origin main"
    exit 1
fi

# Check if already authenticated
if ! gh auth status &> /dev/null; then
    echo "🔐 Please authenticate with GitHub..."
    gh auth login
fi

echo "📦 Creating GitHub repository..."
echo ""

# Create private repository
gh repo create nse-strategy-alerts \
    --private \
    --description "Alert-only NSE stock screening system - No auto-trading" \
    --source=. \
    --remote=origin \
    --push

echo ""
echo "✅ Repository created and code pushed!"
echo ""
echo "📍 Repository URL: https://github.com/NishantPrajapati/nse-strategy-alerts"
echo ""
echo "Next steps:"
echo "1. Review DEPLOYMENT_VPS.md for VPS deployment instructions"
echo "2. Setup .env file with your credentials"
echo "3. Deploy to VPS using Docker Compose"
echo ""
echo "🔒 Security reminder:"
echo "   - Never commit .env file (already in .gitignore)"
echo "   - Keep repository private"
echo "   - Rotate API keys regularly"
