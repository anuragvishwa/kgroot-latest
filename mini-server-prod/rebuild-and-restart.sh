#!/bin/bash
# ============================================================================
# Rebuild and Restart Server Components with Multi-Tenant Support
# ============================================================================

set -e

echo "=========================================="
echo "Rebuilding Server Components"
echo "=========================================="
echo ""

# Navigate to project root
cd "$(dirname "$0")/.."

echo "📦 Step 1: Building new graph-builder image..."
cd kg
docker build -t mini-server-prod-graph-builder:latest -f Dockerfile .

echo ""
echo "=========================================="
echo "Restarting Services"
echo "=========================================="
echo ""

echo "🔄 Step 2: Stopping old graph-builder container..."
docker stop kg-graph-builder 2>/dev/null || echo "Container not running"

echo ""
echo "🗑️  Step 3: Removing old graph-builder container..."
docker rm kg-graph-builder 2>/dev/null || echo "Container not found"

echo ""
echo "🚀 Step 4: Starting updated graph-builder..."
docker run -d \
  --name kg-graph-builder \
  --network compose_kg-network \
  -p 9090:9090 \
  -e KAFKA_BROKERS="kafka:9092" \
  -e KAFKA_GROUP="kg-builder" \
  -e NEO4J_URI="neo4j://neo4j:7687" \
  -e NEO4J_USER="neo4j" \
  -e NEO4J_PASS="${NEO4J_PASSWORD:-anuragvishwa}" \
  -e TOPIC_LOGS="logs.normalized" \
  -e TOPIC_EVENTS="events.normalized" \
  -e TOPIC_ALERTS="alerts.enriched" \
  -e TOPIC_RES="state.k8s.resource" \
  -e TOPIC_TOPO="state.k8s.topology" \
  -e TOPIC_PROM_TARGETS="state.prom.targets" \
  -e TOPIC_PROM_RULES="state.prom.rules" \
  -e RCA_WINDOW_MIN="15" \
  -e METRICS_PORT="9090" \
  --restart unless-stopped \
  mini-server-prod-graph-builder:latest

echo ""
echo "=========================================="
echo "Waiting for service to start..."
echo "=========================================="
sleep 10

echo ""
echo "📊 Container status:"
docker ps | grep kg-graph-builder || echo "Container not running!"

echo ""
echo "📝 Recent logs:"
docker logs --tail=30 kg-graph-builder

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
echo "2. Run: cd mini-server-prod && ./discover-client-ids.sh"
echo "3. If client IDs are found, run: ./generate-multi-client-compose.sh"
echo ""
