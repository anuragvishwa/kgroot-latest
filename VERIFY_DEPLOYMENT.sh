#!/usr/bin/env bash
set -euo pipefail

# Comprehensive Deployment Verification Script
# Run this after deploying KGroot to verify everything works

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function info() { echo -e "${GREEN}✓${NC} $1"; }
function warn() { echo -e "${YELLOW}⚠${NC} $1"; }
function error() { echo -e "${RED}✗${NC} $1"; }
function section() { echo -e "\n${BLUE}=== $1 ===${NC}\n"; }

echo "========================================"
echo "  KGroot Deployment Verification"
echo "========================================"
echo ""

# Step 1: Check Namespace
section "1. Checking Namespaces"
if kubectl get namespace observability &>/dev/null; then
    info "observability namespace exists"
else
    error "observability namespace NOT found"
    echo "Run: kubectl create namespace observability"
    exit 1
fi

# Step 2: Check All Pods
section "2. Checking Pods"
echo "Pods in observability namespace:"
kubectl get pods -n observability

echo ""
echo "Checking pod status..."

required_pods=("kafka-0" "neo4j-0" "kg-builder" "vector" "state-watcher" "alerts-enricher")

for pod in "${required_pods[@]}"; do
    if kubectl get pods -n observability 2>/dev/null | grep -q "$pod.*Running"; then
        info "$pod is Running"
    elif kubectl get pods -n observability 2>/dev/null | grep -q "$pod"; then
        status=$(kubectl get pods -n observability | grep "$pod" | awk '{print $3}')
        warn "$pod is in $status state"
    else
        error "$pod NOT found"
    fi
done

# Step 3: Check Kafka Topics
section "3. Checking Kafka Topics"
echo "Listing Kafka topics..."
if kubectl exec -n observability kafka-0 -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | head -20; then
    topics=$(kubectl exec -n observability kafka-0 -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -v "^$" | wc -l | tr -d ' ')
    info "Found $topics Kafka topics"
else
    error "Cannot list Kafka topics (Kafka may still be starting)"
fi

# Step 4: Check Kafka Consumers
section "4. Checking Kafka Consumers (Message Flow)"
echo "Checking kg-builder consumer group..."
kubectl exec -n observability kafka-0 -- \
    /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --group kg-builder --describe 2>/dev/null || warn "kg-builder consumer group not found (may not have consumed yet)"

echo ""
echo "Checking alerts-enricher consumer group..."
kubectl exec -n observability kafka-0 -- \
    /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --group alerts-enricher-alerts --describe 2>/dev/null || warn "alerts-enricher consumer group not found"

# Step 5: Check Neo4j Connection
section "5. Checking Neo4j Database"
echo "Testing Neo4j connection..."
neo4j_test=$(kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa "RETURN 1 AS test;" 2>&1)

if echo "$neo4j_test" | grep -q "test"; then
    info "Neo4j is accessible and accepting connections"
else
    error "Neo4j connection failed"
    echo "$neo4j_test"
fi

# Step 6: Check Knowledge Graph
section "6. Checking Knowledge Graph (Neo4j Data)"

echo "Counting Resource nodes..."
resource_count=$(kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (r:Resource) RETURN count(r) AS cnt;" 2>/dev/null | tail -1 | tr -d '"' || echo "0")

echo "Counting Episodic nodes..."
episodic_count=$(kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH (e:Episodic) RETURN count(e) AS cnt;" 2>/dev/null | tail -1 | tr -d '"' || echo "0")

echo "Counting POTENTIAL_CAUSE relationships..."
rca_count=$(kubectl exec -n observability neo4j-0 -- \
    cypher-shell -u neo4j -p anuragvishwa \
    "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) AS cnt;" 2>/dev/null | tail -1 | tr -d '"' || echo "0")

if [ "$resource_count" != "0" ]; then
    info "Resource nodes: $resource_count"
else
    warn "No Resource nodes found (may need time to populate)"
fi

if [ "$episodic_count" != "0" ]; then
    info "Episodic nodes: $episodic_count"
else
    warn "No Episodic nodes found (no events yet)"
fi

if [ "$rca_count" != "0" ]; then
    info "POTENTIAL_CAUSE links: $rca_count ✅ RCA is working!"
else
    warn "No POTENTIAL_CAUSE links yet (needs events to correlate)"
fi

# Step 7: Check kg-builder Logs
section "7. Checking kg-builder Logs (Recent Activity)"
echo "Last 10 lines from kg-builder:"
kubectl logs -n observability -l app=kg-builder --tail=10 2>&1 | head -15

# Step 8: Sample Recent Events
section "8. Sampling Recent Events from Kafka"

echo "Checking events.normalized topic..."
kubectl exec -n observability kafka-0 -- \
    kafka-console-consumer.sh --bootstrap-server localhost:9092 \
    --topic events.normalized --max-messages 3 --timeout-ms 3000 2>/dev/null || \
    warn "No messages in events.normalized yet"

echo ""
echo "Checking alerts.normalized topic..."
kubectl exec -n observability kafka-0 -- \
    kafka-console-consumer.sh --bootstrap-server localhost:9092 \
    --topic alerts.normalized --max-messages 3 --timeout-ms 3000 2>/dev/null || \
    warn "No messages in alerts.normalized yet"

# Step 9: Final Summary
section "Summary"

echo "✓ Deployment Status:"
echo "  - Namespace: observability"
echo "  - Kafka Topics: $topics"
echo "  - Neo4j Nodes: $((resource_count + episodic_count))"
echo "  - RCA Links: $rca_count"
echo ""

if [ "$resource_count" -gt "0" ] && [ "$episodic_count" -gt "0" ]; then
    echo -e "${GREEN}✅ KGroot is WORKING! Knowledge graph is being built.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Access Neo4j Browser:"
    echo "     kubectl port-forward -n observability svc/neo4j-external 7474:7474"
    echo "     http://localhost:7474 (neo4j/anuragvishwa)"
    echo ""
    echo "  2. Run test scenarios:"
    echo "     kubectl apply -f test/05-cascading-failure.yaml"
    echo ""
    echo "  3. Query the knowledge graph (in Neo4j Browser):"
    echo "     MATCH (e:Episodic) RETURN e LIMIT 10;"
elif [ "$topics" -gt "10" ]; then
    echo -e "${YELLOW}⚠ KGroot is PARTIALLY working${NC}"
    echo ""
    echo "Kafka is running but Neo4j graph is empty."
    echo "This usually means:"
    echo "  1. kg-builder is not running (check pod status above)"
    echo "  2. No events generated yet (deploy test scenarios)"
    echo "  3. Need to wait a few minutes for data to flow"
    echo ""
    echo "To generate test events:"
    echo "  kubectl apply -f test/05-cascading-failure.yaml"
    echo "  wait 2 minutes"
    echo "  ./VERIFY_DEPLOYMENT.sh"
else
    echo -e "${RED}✗ KGroot is NOT working correctly${NC}"
    echo ""
    echo "Issues detected:"
    echo "  - Kafka topics: $topics (expected 15+)"
    echo "  - Neo4j nodes: $((resource_count + episodic_count))"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check Kafka: kubectl logs -n observability kafka-0 --tail=50"
    echo "  2. Check kg-builder: kubectl logs -n observability -l app=kg-builder --tail=50"
    echo "  3. Check Neo4j: kubectl logs -n observability neo4j-0 --tail=50"
fi

echo ""
echo "========================================"
