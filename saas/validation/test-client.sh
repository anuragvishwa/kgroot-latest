#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# KG RCA CLIENT HEALTH CHECK
# Tests client agent components and data flow
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
CLIENT_ID="${CLIENT_ID:-}"
NAMESPACE="${NAMESPACE:-kg-rca}"

if [ -z "$CLIENT_ID" ]; then
  echo "Usage: $0 --client-id <client-id>"
  echo "   or: CLIENT_ID=<client-id> $0"
  exit 1
fi

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  KG RCA CLIENT HEALTH CHECK"
echo "  Client ID: $CLIENT_ID"
echo "  Namespace: $NAMESPACE"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 1. CHECK KUBERNETES CONNECTIVITY
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[1/6] Checking Kubernetes connectivity...${NC}"
if kubectl cluster-info >/dev/null 2>&1; then
  echo -e "${GREEN}✓ Kubernetes cluster accessible${NC}"
else
  echo -e "${RED}✗ Cannot connect to Kubernetes cluster${NC}"
  exit 1
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 2. CHECK AGENT PODS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[2/6] Checking agent pods...${NC}"

check_pods() {
  local app=$1
  local expected=$2

  local ready=$(kubectl get pods -n "$NAMESPACE" -l app="$app" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

  if [ "$ready" -ge "$expected" ]; then
    echo -e "  ${GREEN}✓ $app: $ready pods running${NC}"
    return 0
  else
    echo -e "  ${RED}✗ $app: $ready pods running (expected >= $expected)${NC}"
    return 1
  fi
}

check_pods "state-watcher" 1 || true
check_pods "vector" 1 || true
check_pods "event-exporter" 1 || true
check_pods "alert-receiver" 1 || true

echo ""

# ───────────────────────────────────────────────────────────────────────────
# 3. CHECK STATE WATCHER
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[3/6] Checking State Watcher...${NC}"

SW_POD=$(kubectl get pods -n "$NAMESPACE" -l app=state-watcher --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -n "$SW_POD" ]; then
  echo -e "${GREEN}✓ State Watcher pod found${NC}"

  # Check logs for activity
  RECENT_LOGS=$(kubectl logs -n "$NAMESPACE" "$SW_POD" --tail=50 2>/dev/null | wc -l)
  if [ "$RECENT_LOGS" -gt 0 ]; then
    echo "  Recent activity: $RECENT_LOGS log lines"
  fi

  # Check for errors
  ERRORS=$(kubectl logs -n "$NAMESPACE" "$SW_POD" --tail=100 2>/dev/null | grep -ic "error" || echo "0")
  if [ "$ERRORS" -gt 5 ]; then
    echo -e "  ${YELLOW}⚠ High error count: $ERRORS${NC}"
  fi
else
  echo -e "${RED}✗ State Watcher pod not found${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 4. CHECK VECTOR LOG COLLECTION
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[4/6] Checking Vector log collection...${NC}"

VECTOR_POD=$(kubectl get pods -n "$NAMESPACE" -l app=vector --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -n "$VECTOR_POD" ]; then
  echo -e "${GREEN}✓ Vector pod found${NC}"

  # Check logs for Kafka connection
  if kubectl logs -n "$NAMESPACE" "$VECTOR_POD" --tail=100 2>/dev/null | grep -q "Connected to Kafka"; then
    echo "  Kafka connection established"
  fi

  # Check for events processed
  EVENTS=$(kubectl logs -n "$NAMESPACE" "$VECTOR_POD" --tail=100 2>/dev/null | grep -c "Processed" || echo "0")
  if [ "$EVENTS" -gt 0 ]; then
    echo "  Events processed: $EVENTS (recent)"
  fi
else
  echo -e "${RED}✗ Vector pod not found${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 5. CHECK EVENT EXPORTER
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[5/6] Checking Event Exporter...${NC}"

EE_POD=$(kubectl get pods -n "$NAMESPACE" -l app=event-exporter --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
if [ -n "$EE_POD" ]; then
  echo -e "${GREEN}✓ Event Exporter pod found${NC}"

  # Check for Kubernetes events being watched
  if kubectl logs -n "$NAMESPACE" "$EE_POD" --tail=50 2>/dev/null | grep -q "Watching"; then
    echo "  Watching Kubernetes events"
  fi

  # Check for recent exports
  EXPORTS=$(kubectl logs -n "$NAMESPACE" "$EE_POD" --tail=100 2>/dev/null | grep -c "Exported" || echo "0")
  if [ "$EXPORTS" -gt 0 ]; then
    echo "  Events exported: $EXPORTS (recent)"
  fi
else
  echo -e "${RED}✗ Event Exporter pod not found${NC}"
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 6. CHECK CONNECTIVITY TO SERVER
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[6/6] Checking connectivity to server...${NC}"

# Get server URL from configmap
SERVER_URL=$(kubectl get configmap -n "$NAMESPACE" kg-rca-agent-config -o jsonpath='{.data.SERVER_URL}' 2>/dev/null || echo "")
if [ -n "$SERVER_URL" ]; then
  echo "  Server URL: $SERVER_URL"

  # Try to connect (requires API key, so just check DNS/network)
  if timeout 5 kubectl run test-connection --rm -i --restart=Never --image=busybox -n "$NAMESPACE" -- wget -q -O- "$SERVER_URL/healthz" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Can reach server${NC}"
  else
    echo -e "${YELLOW}⚠ Cannot reach server (may need API key)${NC}"
  fi
else
  echo -e "${YELLOW}⚠ Server URL not configured${NC}"
fi
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

echo "📊 Agent Status: $RUNNING_PODS/$TOTAL_PODS pods running"
echo ""

if [ "$RUNNING_PODS" -eq "$TOTAL_PODS" ] && [ "$TOTAL_PODS" -gt 0 ]; then
  echo -e "${GREEN}✅ Client agents operational${NC}"
  echo ""
  echo "Next steps:"
  echo "  1. Verify data flow with: ./validate-rca.sh --client-id $CLIENT_ID"
  echo "  2. Check server for RCA links"
  exit 0
else
  echo -e "${YELLOW}⚠️  Some issues detected${NC}"
  echo ""
  echo "For more details, run:"
  echo "  kubectl get pods -n $NAMESPACE"
  echo "  kubectl logs -n $NAMESPACE <pod-name>"
  exit 1
fi
