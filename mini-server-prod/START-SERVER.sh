#!/bin/bash

# ==============================================================================
# KGroot RCA Server Startup Script (13-Topic Production Architecture)
# ==============================================================================

set -e

echo "🚀 Starting KGroot RCA Server (13-Topic Architecture)"
echo "============================================================"

# Step 1: Start Docker Compose
echo ""
echo "📦 Step 1/3: Starting Docker Compose services..."
docker-compose -f docker-compose-control-plane.yml up -d

echo ""
echo "⏳ Waiting for Kafka to be ready..."
sleep 15

# Check Kafka health
docker exec kg-kafka kafka-broker-api-versions --bootstrap-server localhost:29092 > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Kafka is ready"
else
    echo "❌ Kafka failed to start"
    exit 1
fi

# Step 2: Create all Kafka topics
echo ""
echo "📊 Step 2/3: Creating 13 Kafka topics..."
./scripts/create-all-kafka-topics.sh

# Step 3: Verify all services
echo ""
echo "🔍 Step 3/3: Verifying all services..."
echo ""

echo "📋 Docker Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep kg-

echo ""
echo "📊 Kafka Topics (should see 13 topics):"
docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:29092 \
  --list | grep -E "events|logs|alerts|state|raw|cluster|dlq" | wc -l

echo ""
echo "============================================================"
echo "✅ KGroot RCA Server Started Successfully!"
echo ""
echo "🌐 Access Points:"
echo "   - Kafka:               localhost:9092"
echo "   - Neo4j HTTP:          http://localhost:7474"
echo "   - Neo4j Bolt:          bolt://localhost:7687"
echo "   - Webhook Endpoint:    http://localhost:8081/webhook"
echo ""
echo "🔐 Neo4j Credentials:"
echo "   - Username: neo4j"
echo "   - Password: Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA"
echo ""
echo "📊 Services Running:"
echo "   ✅ kg-kafka               - Message broker"
echo "   ✅ kg-neo4j               - Graph database"
echo "   ✅ kg-control-plane       - Dynamic spawning (V2)"
echo "   ✅ kg-topology-builder    - Topology graph"
echo "   ✅ kg-rca-webhook         - Alertmanager receiver"
echo ""
echo "   📝 Note: Event/Log normalizers are spawned PER-CLIENT by control plane"
echo "           (e.g., kg-event-normalizer-{client-id})"
echo ""
echo "📖 Next Steps:"
echo "   1. Test control plane: ./TEST-CONTROL-PLANE-V2.sh"
echo "   2. Check control plane logs: docker logs -f kg-control-plane"
echo "   3. Install client Helm chart (see CLIENT-HELM-DEPLOYMENT.md)"
echo "   4. Watch containers spawn: docker ps | grep kg-"
echo ""
echo "📚 Documentation:"
echo "   - Architecture:  13-TOPIC-ARCHITECTURE.md"
echo "   - Client Setup:  CLIENT-HELM-DEPLOYMENT.md"
echo "   - Monitoring:    docs/MONITORING-GUIDE.md"
echo "============================================================"
