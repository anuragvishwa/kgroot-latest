#!/bin/bash
# ============================================================================
# Check Multi-Tenant Setup Status
# ============================================================================

echo "=========================================="
echo "Multi-Tenant Setup Status Check"
echo "=========================================="
echo ""

echo "📊 Step 1: Check Running Containers"
echo "=========================================="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAME|kg-"

echo ""
echo "📝 Step 2: Check Graph-Builder Status"
echo "=========================================="
if docker ps | grep -q kg-graph-builder; then
    echo "✅ Graph-builder is running"
    echo ""
    echo "Recent logs:"
    docker logs --tail=20 kg-graph-builder 2>&1 | tail -20

    if docker logs kg-graph-builder 2>&1 | grep -q "schema ready"; then
        echo ""
        echo "✅ Graph-builder connected to Neo4j successfully!"
    else
        echo ""
        echo "⚠️  Graph-builder may have connection issues"
    fi
else
    echo "❌ Graph-builder is not running!"
fi

echo ""
echo "📊 Step 3: Check Neo4j Status"
echo "=========================================="
if docker ps | grep -q kg-neo4j; then
    echo "✅ Neo4j is running"
    NEO4J_STATUS=$(docker exec kg-neo4j cypher-shell -u neo4j -p anuragvishwa "RETURN 1" 2>&1 || echo "Connection failed")
    if echo "$NEO4J_STATUS" | grep -q "1"; then
        echo "✅ Neo4j is accessible and responding"
    else
        echo "⚠️  Neo4j authentication may need checking"
        echo "   Try: docker logs kg-neo4j --tail=20"
    fi
else
    echo "❌ Neo4j is not running!"
fi

echo ""
echo "📊 Step 4: Check Kafka Status"
echo "=========================================="
if docker ps | grep -q kg-kafka; then
    echo "✅ Kafka is running"

    echo ""
    echo "Consumer Groups:"
    docker exec kg-kafka kafka-consumer-groups.sh \
        --bootstrap-server localhost:9092 \
        --list 2>/dev/null | grep kg-builder || echo "No kg-builder groups found"
else
    echo "❌ Kafka is not running!"
fi

echo ""
echo "📊 Step 5: Check Client IDs in Topics"
echo "=========================================="
cd "$(dirname "$0")"
./discover-client-ids.sh | grep -A 20 "Summary of All Unique Client IDs"

echo ""
echo "=========================================="
echo "📍 Access URLs"
echo "=========================================="
echo ""
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR-SERVER-IP")
echo "Neo4j Browser:  http://${SERVER_IP}:7474"
echo "                bolt://${SERVER_IP}:7687"
echo "                (user: neo4j, pass: anuragvishwa)"
echo ""
echo "Kafka UI:       http://${SERVER_IP}:7777"
echo "Grafana:        http://${SERVER_IP}:3000"
echo "Prometheus:     http://${SERVER_IP}:9091"
echo "KG API:         http://${SERVER_IP}:8080"
echo "Graph Metrics:  http://${SERVER_IP}:9090/metrics"
echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""

# Check if all 4 topics have client_id
CLIENT_IDS=$(docker exec kg-kafka kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic logs.normalized \
    --max-messages 5 \
    --timeout-ms 5000 2>/dev/null | \
    jq -r 'select(.client_id != null) | .client_id' 2>/dev/null | sort -u | wc -l)

if [ "$CLIENT_IDS" -gt 0 ]; then
    echo "✅ Client IDs detected in Kafka topics"
    echo ""
    echo "Ready for multi-tenant deployment!"
    echo ""
    echo "Run these commands:"
    echo "  1. ./generate-multi-client-compose.sh"
    echo "  2. cd compose"
    echo "  3. docker compose -f docker-compose.yml -f docker-compose.multi-client.yml up -d"
else
    echo "⚠️  No client_ids found yet"
    echo ""
    echo "Wait 2-3 minutes for messages to flow from client cluster,"
    echo "then run: ./discover-client-ids.sh"
fi

echo ""
