#!/bin/bash
# ============================================================================
# Fix and Restart Graph-Builder with Correct Network Settings
# ============================================================================

set -e

echo "=========================================="
echo "Checking Current Infrastructure"
echo "=========================================="
echo ""

echo "📊 Current containers:"
docker ps --format "table {{.Names}}\t{{.Networks}}" | grep -E "NAME|kg-"

echo ""
echo "🔍 Finding Neo4j container..."
NEO4J_CONTAINER=$(docker ps --filter "name=neo4j" --format "{{.Names}}" | head -1)

if [ -z "$NEO4J_CONTAINER" ]; then
    echo "❌ Error: Neo4j container not found!"
    exit 1
fi

echo "✅ Found Neo4j: $NEO4J_CONTAINER"

echo ""
echo "🔍 Finding Kafka container..."
KAFKA_CONTAINER=$(docker ps --filter "name=kafka" --format "{{.Names}}" | head -1)

if [ -z "$KAFKA_CONTAINER" ]; then
    echo "❌ Error: Kafka container not found!"
    exit 1
fi

echo "✅ Found Kafka: $KAFKA_CONTAINER"

echo ""
echo "🔍 Finding network..."
NETWORK=$(docker inspect $NEO4J_CONTAINER --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}')
echo "✅ Network: $NETWORK"

echo ""
echo "=========================================="
echo "Restarting Graph-Builder"
echo "=========================================="
echo ""

echo "🔄 Stopping old graph-builder..."
docker stop kg-graph-builder 2>/dev/null || echo "Not running"
docker rm kg-graph-builder 2>/dev/null || echo "Not found"

echo ""
echo "🚀 Starting graph-builder with correct settings..."
docker run -d \
  --name kg-graph-builder \
  --network "$NETWORK" \
  -p 9090:9090 \
  -e KAFKA_BROKERS="${KAFKA_CONTAINER}:9092" \
  -e KAFKA_GROUP="kg-builder" \
  -e NEO4J_URI="neo4j://${NEO4J_CONTAINER}:7687" \
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
echo "⏳ Waiting 15 seconds for startup..."
sleep 15

echo ""
echo "=========================================="
echo "Status Check"
echo "=========================================="
echo ""

echo "📊 Container status:"
docker ps | grep kg-graph-builder

echo ""
echo "📝 Recent logs:"
docker logs --tail=40 kg-graph-builder

echo ""
echo "=========================================="
echo "✅ Done!"
echo "=========================================="
echo ""
echo "If you see 'schema ready' in the logs above, it's working!"
echo ""
echo "Next steps:"
echo "1. Wait 30 seconds for messages to process"
echo "2. Run: ./discover-client-ids.sh"
echo ""
