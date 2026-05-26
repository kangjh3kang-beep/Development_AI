#!/bin/bash
# =========================================================================
# PropAI v49.0 - Unified Docker Build & Push Pipeline
# =========================================================================

set -e

VERSION="v49.0"
API_IMAGE="propai-api:$VERSION"
WEB_IMAGE="propai-web:$VERSION"

echo "========================================"
echo "🚀 Starting Docker Build Pipeline: $VERSION"
echo "========================================"

# 1. Build Backend API Image
echo "[1/4] Building Backend API Image ($API_IMAGE)..."
docker build -t $API_IMAGE -f apps/api/Dockerfile .

# 2. Build Frontend Web Image
echo "[2/4] Building Frontend Web Image ($WEB_IMAGE)..."
docker build -t $WEB_IMAGE -f apps/web/Dockerfile .

# 3. Output Validation
echo "[3/4] Validating Docker Images..."
docker images | grep propai-

echo "[4/4] 📦 Build Complete!"
echo "To deploy locally using production compose, run:"
echo "docker-compose -f docker-compose.prod.yml up -d"
