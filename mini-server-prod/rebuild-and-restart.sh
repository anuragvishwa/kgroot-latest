#!/bin/bash
# ============================================================================
# Rebuild and Restart Server Components with Multi-Tenant Support
# ============================================================================

set -e

echo "=========================================="
echo "Rebuilding Server Components"
echo "=========================================="
echo ""

# Navigate to mini-server-prod
cd "$(dirname "$0")"

echo "📦 Rebuilding graph-builder with client_id support..."
cd compose
docker compose build graph-builder

echo ""
echo "=========================================="
echo "Restarting Services"
echo "=========================================="
echo ""

echo "🔄 Stopping old graph-builder..."
docker compose stop graph-builder

echo ""
echo "🚀 Starting updated graph-builder..."
docker compose up -d graph-builder

echo ""
echo "=========================================="
echo "Waiting for service to be healthy..."
echo "=========================================="
sleep 10

echo ""
docker compose ps graph-builder

echo ""
echo "=========================================="
echo "✅ Rebuild Complete!"
echo "=========================================="
echo ""
echo "⚠️  IMPORTANT: State-watcher runs in CLIENT K8s clusters"
echo ""
echo "To get state.k8s.resource and state.k8s.topology with client_id:"
echo "1. Deploy/upgrade state-watcher in client K8s clusters"
echo "2. It will automatically add CLIENT_ID to all messages"
echo ""
echo "Next steps:"
echo "1. Wait 30 seconds for new log messages to flow"
echo "2. Run: ./discover-client-ids.sh"
echo "3. If client IDs are found, run: ./generate-multi-client-compose.sh"
echo ""
