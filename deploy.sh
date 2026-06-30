#!/bin/bash
set -e
cd /opt/BreakMyApp

echo "Stashing any local changes (safety net)..."
git stash --include-untracked

echo "Pulling latest..."
git pull origin main

echo "Restoring stashed changes if any conflict-free ones remain..."
git stash pop || true

echo "Rebuilding and restarting services..."
docker compose -f docker-compose.prod.yml up -d --build

echo "Deploy complete."
docker compose -f docker-compose.prod.yml ps
