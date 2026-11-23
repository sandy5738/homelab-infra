#!/usr/bin/env bash
# ==============================================================================
# Deployment Script: AutoRox × Whatomate Inventory Copilot
# Syncs code, master data, and Docker configurations to your home server.
# ==============================================================================

set -euo pipefail

# Default target server (adjust or override via env: TARGET_HOST=user@host ./deploy_to_server.sh)
TARGET_HOST="${TARGET_HOST:-sandy@enma}"
TARGET_DIR="${TARGET_DIR:-~/autorox-inventory}"

echo "============================================================"
echo "🚀 Deploying AutoRox Inventory Copilot to: ${TARGET_HOST}:${TARGET_DIR}"
echo "============================================================"

# Ensure remote destination directory exists
ssh "${TARGET_HOST}" "mkdir -p ${TARGET_DIR}"

# Rsync project files, excluding cache, git, and local binaries
rsync -avz --delete \
  --exclude='.git' \
  --exclude='engine/autorox-engine' \
  --exclude='data/live/*.db-journal' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  ./ "${TARGET_HOST}:${TARGET_DIR}/"

echo "✅ Code & Data synchronized successfully."

# Provide remote start command
echo ""
echo "============================================================"
echo "🎯 Next Steps on ${TARGET_HOST}:"
echo "============================================================"
echo "1. Connect to server:"
echo "   ssh ${TARGET_HOST}"
echo ""
echo "2. Navigate to project directory:"
echo "   cd ${TARGET_DIR}"
echo ""
echo "3. Configure environment variables (if not done yet):"
echo "   cp .env.example .env && nano .env"
echo ""
echo "4. Build and start services in Docker:"
echo "   docker compose up -d --build"
echo ""
echo "5. Check service logs:"
echo "   docker compose logs -f autorox-engine"
echo "============================================================"
