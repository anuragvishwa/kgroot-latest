#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# KG RCA SERVER DEPLOYMENT SCRIPT
# Deploys the complete KG RCA server infrastructure
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default configuration
NAMESPACE="kg-rca-server"
RELEASE_NAME="kg-rca-server"
VALUES_FILE=""
DRY_RUN=false
SKIP_VALIDATION=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --release)
      RELEASE_NAME="$2"
      shift 2
      ;;
    --values)
      VALUES_FILE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-validation)
      SKIP_VALIDATION=true
      shift
      ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --namespace NAME      Kubernetes namespace (default: kg-rca-server)"
      echo "  --release NAME        Helm release name (default: kg-rca-server)"
      echo "  --values FILE         Values file (default: values.yaml)"
      echo "  --dry-run             Perform dry-run without actual deployment"
      echo "  --skip-validation     Skip pre-deployment validation"
      echo "  --help                Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  KG RCA SERVER DEPLOYMENT"
echo "  Namespace: $NAMESPACE"
echo "  Release: $RELEASE_NAME"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 1. PRE-DEPLOYMENT VALIDATION
# ───────────────────────────────────────────────────────────────────────────
if [ "$SKIP_VALIDATION" = false ]; then
  echo -e "${BLUE}[1/5] Pre-deployment validation...${NC}"

  # Check kubectl
  if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}✗ kubectl not found${NC}"
    exit 1
  fi
  echo -e "${GREEN}✓ kubectl installed${NC}"

  # Check helm
  if ! command -v helm &> /dev/null; then
    echo -e "${RED}✗ helm not found${NC}"
    exit 1
  fi
  echo -e "${GREEN}✓ helm installed${NC}"

  # Check cluster connectivity
  if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}✗ Cannot connect to Kubernetes cluster${NC}"
    exit 1
  fi
  echo -e "${GREEN}✓ Kubernetes cluster accessible${NC}"

  # Check for required storage classes
  if kubectl get storageclass fast-ssd &> /dev/null; then
    echo -e "${GREEN}✓ Storage class 'fast-ssd' available${NC}"
  else
    echo -e "${YELLOW}⚠ Storage class 'fast-ssd' not found - using default${NC}"
  fi

  echo ""
fi

# ───────────────────────────────────────────────────────────────────────────
# 2. CREATE NAMESPACE
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[2/5] Creating namespace...${NC}"

if kubectl get namespace "$NAMESPACE" &> /dev/null; then
  echo -e "${YELLOW}⚠ Namespace already exists: $NAMESPACE${NC}"
else
  if [ "$DRY_RUN" = false ]; then
    kubectl create namespace "$NAMESPACE"
    echo -e "${GREEN}✓ Created namespace: $NAMESPACE${NC}"
  else
    echo "Would create namespace: $NAMESPACE"
  fi
fi
echo ""

# ───────────────────────────────────────────────────────────────────────────
# 3. INSTALL HELM CHART
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[3/5] Installing Helm chart...${NC}"

# Locate chart directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="$SCRIPT_DIR/../server/helm-chart/kg-rca-server"

if [ ! -d "$CHART_DIR" ]; then
  echo -e "${RED}✗ Chart directory not found: $CHART_DIR${NC}"
  exit 1
fi

# Build helm command
HELM_CMD="helm install $RELEASE_NAME $CHART_DIR --namespace $NAMESPACE --create-namespace"

if [ -n "$VALUES_FILE" ]; then
  if [ ! -f "$VALUES_FILE" ]; then
    echo -e "${RED}✗ Values file not found: $VALUES_FILE${NC}"
    exit 1
  fi
  HELM_CMD="$HELM_CMD --values $VALUES_FILE"
fi

if [ "$DRY_RUN" = true ]; then
  HELM_CMD="$HELM_CMD --dry-run --debug"
fi

# Execute helm install
echo "Executing: $HELM_CMD"
echo ""

if eval "$HELM_CMD"; then
  if [ "$DRY_RUN" = false ]; then
    echo -e "${GREEN}✓ Helm chart installed successfully${NC}"
  else
    echo -e "${GREEN}✓ Dry-run successful${NC}"
  fi
else
  echo -e "${RED}✗ Helm installation failed${NC}"
  exit 1
fi
echo ""

if [ "$DRY_RUN" = true ]; then
  echo "Dry-run completed. No actual deployment was performed."
  exit 0
fi

# ───────────────────────────────────────────────────────────────────────────
# 4. WAIT FOR PODS
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[4/5] Waiting for pods to be ready...${NC}"
echo "This may take several minutes..."
echo ""

# Wait for critical components
wait_for_pods() {
  local app=$1
  local timeout=300

  echo -n "Waiting for $app..."

  for i in $(seq 1 $timeout); do
    READY=$(kubectl get pods -n "$NAMESPACE" -l app="$app" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [ "$READY" -gt 0 ]; then
      echo -e " ${GREEN}✓ Ready ($READY pods)${NC}"
      return 0
    fi
    echo -n "."
    sleep 1
  done

  echo -e " ${RED}✗ Timeout${NC}"
  return 1
}

wait_for_pods "neo4j" || true
wait_for_pods "zookeeper" || true
wait_for_pods "kafka" || true
wait_for_pods "graph-builder" || true
wait_for_pods "kg-api" || true

echo ""

# ───────────────────────────────────────────────────────────────────────────
# 5. POST-DEPLOYMENT VERIFICATION
# ───────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[5/5] Post-deployment verification...${NC}"

# Check pod status
TOTAL_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

echo "Pod Status: $RUNNING_PODS/$TOTAL_PODS running"

# Check services
SERVICES=$(kubectl get svc -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
echo "Services: $SERVICES created"

# Get service endpoints
echo ""
echo "Service Endpoints:"
kubectl get svc -n "$NAMESPACE" -o wide

echo ""

# ──���────────────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  DEPLOYMENT SUMMARY"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

if [ "$RUNNING_PODS" -eq "$TOTAL_PODS" ] && [ "$TOTAL_PODS" -gt 0 ]; then
  echo -e "${GREEN}✅ Deployment successful!${NC}"
  echo ""
  echo "Next steps:"
  echo "  1. Verify health: ./test-server.sh"
  echo "  2. Access Neo4j: kubectl port-forward -n $NAMESPACE svc/$RELEASE_NAME-neo4j 7474:7474"
  echo "  3. Access API: kubectl port-forward -n $NAMESPACE svc/$RELEASE_NAME-kg-api 8080:8080"
  echo "  4. Onboard first client: ./onboard-client.sh"
  exit 0
else
  echo -e "${YELLOW}⚠️  Deployment completed with warnings${NC}"
  echo ""
  echo "Some pods are not running. Check status with:"
  echo "  kubectl get pods -n $NAMESPACE"
  echo "  kubectl describe pod -n $NAMESPACE <pod-name>"
  exit 1
fi
