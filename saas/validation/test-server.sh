#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# KG RCA SERVER HEALTH CHECK
# Tests all server components and verifies functionality
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
NAMESPACE="${NAMESPACE:-kg-rca-server}"
RELEASE_NAME="${RELEASE_NAME:-kg-rca-server}"

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  KG RCA SERVER HEALTH CHECK"
echo "  Namespace: $NAMESPACE"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 1. CHECK KUBERNETES CONNECTIVITY
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[1/8] Checking Kubernetes connectivity...${NC}"
if kubectl cluster-info >/dev/null 2>&1; then
  echo -e "${GREEN}✓ Kubernetes cluster accessible${NC}"
else
  echo -e "${RED}✗ Cannot connect to Kubernetes cluster${NC}"
  exit 1
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 2. CHECK NAMESPACE
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[2/8] Checking namespace...${NC}"
if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  echo -e "${GREEN}✓ Namespace exists: $NAMESPACE${NC}"
else
  echo -e "${RED}✗ Namespace not found: $NAMESPACE${NC}"
  exit 1
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 3. CHECK POD STATUS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[3/8] Checking pod status...${NC}"

check_pods() {
  local app=$1
  local expected=$2

  local ready=$(kubectl get pods -n "$NAMESPACE" -l app="$app" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

  if [ "$ready" -ge "$expected" ]; then
    echo -e "  ${GREEN}✓ $app: $ready/$expected pods running${NC}"
    return 0
  else
    echo -e "  ${RED}✗ $app: $ready/$expected pods running${NC}"
    return 1
  fi
}

check_pods "neo4j" 1 || true
check_pods "kafka" 1 || true
check_pods "zookeeper" 1 || true
check_pods "graph-builder" 1 || true
check_pods "kg-api" 1 || true

echo ""

# ───────────────────────────────────────────────────────────────────────────
# 4. CHECK NEO4J
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[4/8] Checking Neo4j...${NC}"

NEO4J_POD=$(kubectl get pods -n "$NAMESPACE" -l app=neo4j --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -n "$NEO4J_POD" ]; then
  if kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Neo4j responding${NC}"

    # Get node count
    NODE_COUNT=$(kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain "MATCH (n) RETURN count(n) as count" 2>/dev/null | tail -1 || echo "0")
    echo "  Nodes: $NODE_COUNT"

    # Get RCA count
    RCA_COUNT=$(kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r) as count" 2>/dev/null | tail -1 || echo "0")
    echo "  RCA Links: $RCA_COUNT"
  else
    echo -e "${RED}✗ Neo4j not responding${NC}"
  fi
else
  echo -e "${RED}✗ Neo4j pod not found${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 5. CHECK KAFKA
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[5/8] Checking Kafka...${NC}"

KAFKA_POD=$(kubectl get pods -n "$NAMESPACE" -l app=kafka --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -n "$KAFKA_POD" ]; then
  if kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Kafka responding${NC}"

    # List topics
    TOPICS=$(kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l)
    echo "  Topics: $TOPICS"

    # Check consumer groups
    GROUPS=$(kubectl exec -n "$NAMESPACE" "$KAFKA_POD" -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l)
    echo "  Consumer Groups: $GROUPS"
  else
    echo -e "${RED}✗ Kafka not responding${NC}"
  fi
else
  echo -e "${RED}✗ Kafka pod not found${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 6. CHECK GRAPH BUILDER
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[6/8] Checking Graph Builder...${NC}"

BUILDER_POD=$(kubectl get pods -n "$NAMESPACE" -l app=graph-builder --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -n "$BUILDER_POD" ]; then
  if kubectl exec -n "$NAMESPACE" "$BUILDER_POD" -- wget -q -O- http://localhost:9090/healthz >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Graph Builder healthy${NC}"

    # Get metrics
    METRICS=$(kubectl exec -n "$NAMESPACE" "$BUILDER_POD" -- wget -q -O- http://localhost:9090/metrics 2>/dev/null | grep -c "^kg_" || echo "0")
    echo "  Metrics exposed: $METRICS"
  else
    echo -e "${YELLOW}⚠ Graph Builder health check failed${NC}"
  fi
else
  echo -e "${RED}✗ Graph Builder pod not found${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 7. CHECK KG API
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[7/8] Checking KG API...${NC}"

API_POD=$(kubectl get pods -n "$NAMESPACE" -l app=kg-api --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -n "$API_POD" ]; then
  if kubectl exec -n "$NAMESPACE" "$API_POD" -- wget -q -O- http://localhost:8080/healthz >/dev/null 2>&1; then
    echo -e "${GREEN}✓ KG API healthy${NC}"

    # Test stats endpoint
    STATS=$(kubectl exec -n "$NAMESPACE" "$API_POD" -- wget -q -O- http://localhost:8080/api/v1/stats 2>/dev/null)
    if [ -n "$STATS" ]; then
      echo "  Stats API responding"
    fi
  else
    echo -e "${YELLOW}⚠ KG API health check failed${NC}"
  fi
else
  echo -e "${RED}✗ KG API pod not found${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 8. CHECK SERVICES
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[8/8] Checking services...${NC}"

check_service() {
  local svc=$1
  if kubectl get svc -n "$NAMESPACE" "$RELEASE_NAME-$svc" >/dev/null 2>&1; then
    local type=$(kubectl get svc -n "$NAMESPACE" "$RELEASE_NAME-$svc" -o jsonpath='{.spec.type}')
    local port=$(kubectl get svc -n "$NAMESPACE" "$RELEASE_NAME-$svc" -o jsonpath='{.spec.ports[0].port}')
    echo -e "  ${GREEN}✓ $svc: $type:$port${NC}"
  else
    echo -e "  ${YELLOW}⚠ $svc: not found${NC}"
  fi
}

check_service "neo4j"
check_service "kafka"
check_service "graph-builder"
check_service "kg-api"

echo ""

# ───────────────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  HEALTH CHECK SUMMARY"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# Count running pods
TOTAL_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

echo "📊 Pod Status: $RUNNING_PODS/$TOTAL_PODS running"

if [ "$RUNNING_PODS" -eq "$TOTAL_PODS" ] && [ "$TOTAL_PODS" -gt 0 ]; then
  echo -e "${GREEN}✅ All systems operational${NC}"
  exit 0
else
  echo -e "${YELLOW}⚠️  Some issues detected${NC}"
  echo ""
  echo "For more details, run:"
  echo "  kubectl get pods -n $NAMESPACE"
  echo "  kubectl logs -n $NAMESPACE <pod-name>"
  exit 1
fi
