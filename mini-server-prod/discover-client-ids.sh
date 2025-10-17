#!/bin/bash
# ============================================================================
# Discover Client IDs from Kafka Topics
# ============================================================================
# This script samples messages from Kafka topics to identify unique client_ids
# that are actually sending data to the system.
# ============================================================================

set -e

echo "=========================================="
echo "Discovering Client IDs in Kafka Topics"
echo "=========================================="
echo ""

TOPICS=("logs.normalized" "events.normalized" "state.k8s.resource" "state.k8s.topology")
SAMPLE_SIZE=100

declare -A ALL_CLIENT_IDS

for TOPIC in "${TOPICS[@]}"; do
    echo "📊 Sampling topic: $TOPIC"

    # Check if topic exists
    if ! docker exec kg-kafka kafka-topics.sh \
        --bootstrap-server localhost:9092 \
        --list 2>/dev/null | grep -q "^${TOPIC}$"; then
        echo "   ⚠️  Topic does not exist yet"
        echo ""
        continue
    fi

    # Get sample messages and extract client_ids
    # Note: Messages have format: {"Value": "{...}", ...}
    # The actual data is in the Value field as a JSON string
    # We need to run jq on the host, not in the kafka container
    CLIENT_IDS=$(docker exec kg-kafka kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 \
        --topic "$TOPIC" \
        --max-messages "$SAMPLE_SIZE" \
        --from-beginning \
        --timeout-ms 5000 2>/dev/null | \
        jq -r 'select(.Value != null) | .Value | fromjson | select(.client_id != null) | .client_id' 2>/dev/null | \
        sort -u || true)

    if [ -z "$CLIENT_IDS" ]; then
        echo "   ⚠️  No client_id found in messages"
    else
        echo "   ✅ Found client_id(s):"
        echo "$CLIENT_IDS" | while read -r cid; do
            if [ -n "$cid" ]; then
                echo "      - $cid"
                ALL_CLIENT_IDS["$cid"]=1
            fi
        done
    fi
    echo ""
done

echo "=========================================="
echo "Summary of All Unique Client IDs"
echo "=========================================="
echo ""

if [ ${#ALL_CLIENT_IDS[@]} -eq 0 ]; then
    echo "❌ No client_ids found in any topic!"
    echo ""
    echo "This means either:"
    echo "  1. No messages have been sent yet"
    echo "  2. Messages don't have a 'client_id' field"
    echo "  3. Client-side Vector is not configured with client.id"
    echo ""
    echo "Next steps:"
    echo "  - Check client-light/helm-chart/values.yaml"
    echo "  - Ensure 'client.id' is set in the configuration"
    echo "  - Deploy/update the client-side Helm chart"
    exit 0
fi

echo "Found ${#ALL_CLIENT_IDS[@]} unique client ID(s):"
echo ""
for client_id in "${!ALL_CLIENT_IDS[@]}"; do
    echo "  • $client_id"
done

echo ""
echo "=========================================="
echo "Recommended docker-compose Configuration"
echo "=========================================="
echo ""
echo "Create a custom docker-compose.multi-client.yml with:"
echo ""

port=9091
for client_id in "${!ALL_CLIENT_IDS[@]}"; do
    # Sanitize client_id for service name (replace special chars with hyphens)
    service_name=$(echo "$client_id" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')

    cat <<EOF
  graph-builder-${service_name}:
    build:
      context: ../kg
      dockerfile: Dockerfile
    container_name: kg-graph-builder-${service_name}
    environment:
      CLIENT_ID: ${client_id}
      KAFKA_BROKERS: \${KAFKA_ADVERTISED_HOST}:9092
      KAFKA_GROUP: kg-builder
      NEO4J_URI: neo4j://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASS: \${NEO4J_PASSWORD}
      # ... (other env vars)
    ports:
      - "${port}:9090"
    networks:
      - kg-network
    depends_on:
      kafka:
        condition: service_healthy
      neo4j:
        condition: service_healthy

EOF
    ((port++))
done

echo ""
echo "=========================================="
echo "Deployment Command"
echo "=========================================="
echo ""
echo "docker compose -f docker-compose.yml -f docker-compose.multi-client.yml up -d"
echo ""
