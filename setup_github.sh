#!/bin/bash

# NSE Strategy Alerts - GitHub Setup Script
# This script helps push code to your personal GitHub account

set -e

echo "🚀 NSE Strategy Alerts - GitHub Setup"
echo "======================================"
echo ""

# Check if remote is already set
if git remote get-url origin &> /dev/null; then
    CURRENT_REMOTE=$(git remote get-url origin)
    echo "📍 Current remote: $CURRENT_REMOTE"
    echo ""
    
    if [[ $CURRENT_REMOTE == *"github.com"* ]]; then
        echo "✅ Remote already configured for github.com"
        echo ""
        read -p "Do you want to push to GitHub now? (y/n) " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "📤 Pushing to GitHub..."
            git push -u origin main
            echo ""
            echo "✅ Code pushed successfully!"
            echo "📍 Repository: https://github.com/NishantPrajapati/nse-strategy-alerts"
        fi
        exit 0
    fi
fi

echo "⚠️  Manual GitHub Setup Required"
echo ""
echo "Steps to push to your personal GitHub:"
echo ""
echo "1. Create a new PRIVATE repository on GitHub:"
echo "   → Go to: https://github.com/new"
echo "   → Repository name: nse-strategy-alerts"
echo "   → Make it PRIVATE (recommended for trading strategies)"
echo "   → Don't initialize with README, .gitignore, or license"
echo ""
echo "2. Push your code:"
echo "   git push -u origin main"
echo ""
echo "3. Verify on GitHub:"
echo "   https://github.com/NishantPrajapati/nse-strategy-alerts"
echo ""
echo "🔒 Security reminders:"
echo "   - Repository is set to PRIVATE"
echo "   - .env file is in .gitignore (never committed)"
echo "   - Keep API keys secure"
echo ""