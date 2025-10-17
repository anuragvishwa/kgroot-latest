#!/bin/bash
# ============================================================================
# Deploy Multi-Client Graph Builders
# ============================================================================
# This script deploys graph-builder containers for each discovered client_id
# without recreating existing infrastructure (Neo4j, Kafka, etc.)
# ============================================================================

set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "Deploying Multi-Client Graph Builders"
echo "=========================================="
echo ""

# First, generate the configuration
./generate-multi-client-compose.sh

echo ""
echo "=========================================="
echo "Starting Graph Builders"
echo "=========================================="
echo ""

# Extract Neo4j password from running container
NEO4J_CONTAINER=$(docker ps --filter "name=neo4j" --format "{{.Names}}" | head -1)
if [ -z "$NEO4J_CONTAINER" ]; then
    echo "❌ Neo4j container not found!"
    exit 1
fi

NEO4J_PASS=$(docker inspect $NEO4J_CONTAINER --format='{{range .Config.Env}}{{println .}}{{end}}' | grep NEO4J_AUTH | cut -d'/' -f2 || echo "anuragvishwa")
echo "✅ Found Neo4j password"

# Get Kafka container
KAFKA_CONTAINER=$(docker ps --filter "name=kafka" --format "{{.Names}}" | grep -v proxy | head -1)
if [ -z "$KAFKA_CONTAINER" ]; then
    echo "❌ Kafka container not found!"
    exit 1
fi
echo "✅ Found Kafka container: $KAFKA_CONTAINER"

# Get network
NETWORK=$(docker inspect $NEO4J_CONTAINER --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}')
echo "✅ Using network: $NETWORK"

# Get actual Neo4j and Kafka container names for connection
NEO4J_NAME=$(docker ps --filter "name=neo4j" --format "{{.Names}}" | head -1)
KAFKA_NAME=$(docker ps --filter "name=kafka" --format "{{.Names}}" | grep -v proxy | head -1)

echo ""

# Discover client IDs
TOPICS=("logs.normalized" "events.normalized" "state.k8s.resource" "state.k8s.topology")
SAMPLE_SIZE=100

declare -A ALL_CLIENT_IDS

echo "🔍 Discovering client IDs..."
for TOPIC in "${TOPICS[@]}"; do
    CLIENT_IDS=$(docker exec $KAFKA_CONTAINER kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 \
        --topic "$TOPIC" \
        --max-messages "$SAMPLE_SIZE" \
        --timeout-ms 5000 2>/dev/null | \
        jq -r 'select(.client_id != null) | .client_id' 2>/dev/null | \
        sort -u || true)

    if [ -n "$CLIENT_IDS" ]; then
        while IFS= read -r cid; do
            if [ -n "$cid" ]; then
                ALL_CLIENT_IDS["$cid"]=1
            fi
        done <<< "$CLIENT_IDS"
    fi
done

if [ ${#ALL_CLIENT_IDS[@]} -eq 0 ]; then
    echo "❌ No client_ids found in Kafka topics!"
    exit 1
fi

echo "✅ Found ${#ALL_CLIENT_IDS[@]} client ID(s): ${!ALL_CLIENT_IDS[@]}"
echo ""

# Build the graph-builder image if needed
echo "🔨 Building graph-builder image..."
cd ../kg
docker build -t mini-server-prod-graph-builder:latest -f Dockerfile . > /dev/null 2>&1
cd ../mini-server-prod
echo "✅ Image built"
echo ""

# Deploy a container for each client_id
PORT=9095  # Start from 9095 to avoid conflicts with Prometheus (9091)
for client_id in "${!ALL_CLIENT_IDS[@]}"; do
    service_name=$(echo "$client_id" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')
    container_name="kg-graph-builder-${service_name}"

    echo "🚀 Deploying graph-builder for client: $client_id"

    # Stop and remove if exists
    docker stop "$container_name" 2>/dev/null || true
    docker rm "$container_name" 2>/dev/null || true

    # Start new container
    docker run -d \
        --name "$container_name" \
        --network "$NETWORK" \
        -p "${PORT}:9090" \
        -e CLIENT_ID="$client_id" \
        -e KAFKA_BROKERS="${KAFKA_NAME}:9092" \
        -e KAFKA_GROUP="kg-builder-${service_name}" \
        -e NEO4J_URI="neo4j://${NEO4J_NAME}:7687" \
        -e NEO4J_USER="neo4j" \
        -e NEO4J_PASS="$NEO4J_PASS" \
        -e TOPIC_LOGS="logs.normalized" \
        -e TOPIC_EVENTS="events.normalized" \
        -e TOPIC_ALERTS="alerts.enriched" \
        -e TOPIC_RES="state.k8s.resource" \
        -e TOPIC_TOPO="state.k8s.topology" \
        -e TOPIC_PROM_TARGETS="state.prom.targets" \
        -e TOPIC_PROM_RULES="state.prom.rules" \
        -e RCA_WINDOW_MIN="15" \
        -e SEVERITY_ESCALATION_ENABLED="true" \
        -e SEVERITY_ESCALATION_WINDOW_MIN="5" \
        -e SEVERITY_ESCALATION_THRESHOLD="3" \
        -e INCIDENT_CLUSTERING_ENABLED="true" \
        -e ANOMALY_DETECTION_ENABLED="true" \
        -e METRICS_PORT="9090" \
        -e LOG_LEVEL="info" \
        --restart unless-stopped \
        mini-server-prod-graph-builder:latest

    echo "   ✅ Container started: $container_name (metrics on port $PORT)"

    ((PORT++))
done

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Verify containers:"
echo "  docker ps | grep graph-builder"
echo ""
echo "Check logs:"
for client_id in "${!ALL_CLIENT_IDS[@]}"; do
    service_name=$(echo "$client_id" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')
    echo "  docker logs -f kg-graph-builder-${service_name}"
done
echo ""
echo "Check consumer groups:"
echo "  docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \\"
echo "    --bootstrap-server localhost:9092 --list | grep kg-builder"
echo ""
