#!/usr/bin/env bash
set -euo pipefail

# KGroot Full Deployment Script
# Deploys entire observability stack with knowledge graph RCA

echo "========================================"
echo "  KGroot Deployment - Full Stack"
echo "========================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

function error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

function wait_for_pods() {
    local namespace=$1
    local label=$2
    local timeout=${3:-300}

    info "Waiting for pods with label $label in namespace $namespace..."
    kubectl wait --for=condition=ready pod -l "$label" -n "$namespace" --timeout="${timeout}s" || {
        error "Timeout waiting for pods"
        return 1
    }
}

# Check prerequisites
info "Checking prerequisites..."

if ! command -v kubectl &> /dev/null; then
    error "kubectl not found. Please install kubectl first."
    exit 1
fi

if ! command -v helm &> /dev/null; then
    error "helm not found. Please install helm first."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    error "docker not found. Please install docker first."
    exit 1
fi

if ! command -v minikube &> /dev/null; then
    warn "minikube not found. Assuming running on different K8s cluster."
fi

info "All prerequisites met!"
echo ""

# Step 1: Install Prometheus Stack
info "Step 1/9: Installing Prometheus Stack..."
echo ""

if helm list -n monitoring | grep -q prometheus; then
    warn "Prometheus already installed. Skipping..."
else
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
    helm repo update

    helm install prometheus prometheus-community/kube-prometheus-stack \
      --namespace monitoring \
      --create-namespace \
      -f k8s/prom-values.yaml \
      --wait --timeout=600s

    info "Prometheus installed successfully!"
fi

echo ""

# Step 2: Deploy Kafka
info "Step 2/9: Deploying Kafka..."
echo ""

kubectl apply -f k8s/kafka.yaml

info "Waiting for Kafka to be ready (this may take 2-3 minutes)..."
wait_for_pods observability app=kafka 600

# Wait for kafka-init job to complete
info "Waiting for Kafka topics to be created..."
kubectl wait --for=condition=complete job/kafka-init -n observability --timeout=300s || {
    warn "Kafka init job did not complete. Topics may need manual creation."
}

info "Kafka deployed successfully!"
echo ""

# Step 3: Verify Kafka Topics
info "Step 3/9: Verifying Kafka topics..."
echo ""

TOPICS=$(kubectl exec -n observability kafka-0 -- \
    kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | grep -v "^$" | wc -l)

if [ "$TOPICS" -gt 10 ]; then
    info "Found $TOPICS Kafka topics"
else
    warn "Expected more topics. Found only $TOPICS. Check kafka-init logs."
fi

echo ""

# Step 4: Deploy Neo4j
info "Step 4/9: Deploying Neo4j..."
echo ""

kubectl apply -f k8s/neo4j.yaml

info "Waiting for Neo4j to be ready (this may take 1-2 minutes)..."
wait_for_pods observability app=neo4j 600

info "Neo4j deployed successfully!"
echo ""

# Step 5: Deploy ConfigMap and kg-builder
info "Step 5/9: Deploying kg-builder..."
echo ""

# Build kg-builder image if needed
if command -v minikube &> /dev/null; then
    info "Building kg-builder Docker image..."
    cd kg

    # Generate go.sum if missing
    if [ ! -f go.sum ]; then
        info "Generating go.sum..."
        go mod download
        go mod tidy
    fi

    docker build -t anuragvishwa/kg-builder:latest .
    minikube image load anuragvishwa/kg-builder:latest

    cd ..
    info "kg-builder image built and loaded into Minikube!"
else
    warn "Not using Minikube. Make sure kg-builder image is available in your registry."
fi

# Deploy kg-builder
kubectl apply -f k8s/kg-builder.yaml

info "Waiting for kg-builder to be ready..."
sleep 10  # Give it time to pull image and start
wait_for_pods observability app=kg-builder 300 || {
    warn "kg-builder may not be ready yet. Check logs with: kubectl logs -n observability -l app=kg-builder"
}

info "kg-builder deployed successfully!"
echo ""

# Step 6: Deploy Vector
info "Step 6/9: Deploying Vector (events/alerts normalization)..."
echo ""

kubectl apply -f k8s/vector-configmap.yaml

info "Waiting for Vector deployment..."
wait_for_pods observability app=vector 300

info "Waiting for Vector DaemonSet..."
sleep 5
kubectl rollout status daemonset/vector-logs -n observability --timeout=300s || {
    warn "Vector DaemonSet rollout may not be complete"
}

info "Vector deployed successfully!"
echo ""

# Step 7: Deploy state-watcher
info "Step 7/9: Deploying state-watcher..."
echo ""

kubectl apply -f k8s/state-watcher.yaml

info "Waiting for state-watcher to be ready..."
wait_for_pods observability app=state-watcher 300

info "state-watcher deployed successfully!"
echo ""

# Step 8: Deploy K8s event exporter
info "Step 8/9: Deploying K8s event exporter..."
echo ""

if [ -f k8s/k8s-event-exporter.yaml ]; then
    kubectl apply -f k8s/k8s-event-exporter.yaml
    wait_for_pods observability app=k8s-event-exporter 300 || {
        warn "K8s event exporter may not be ready"
    }
    info "K8s event exporter deployed!"
else
    warn "k8s/k8s-event-exporter.yaml not found. Skipping..."
fi

echo ""

# Step 9: Deploy alerts-enricher
info "Step 9/9: Deploying alerts-enricher..."
echo ""

if command -v minikube &> /dev/null; then
    cd alerts-enricher
    if [ -f build-and-deploy.sh ]; then
        info "Building alerts-enricher..."
        ./build-and-deploy.sh
    else
        warn "build-and-deploy.sh not found. Skipping alerts-enricher build."
    fi
    cd ..
else
    warn "Not using Minikube. Ensure alerts-enricher image is available."
fi

kubectl apply -f k8s/alerts-enricher.yaml

info "Waiting for alerts-enricher to be ready..."
wait_for_pods observability app=alerts-enricher 300 || {
    warn "alerts-enricher may not be ready. Check logs."
}

info "alerts-enricher deployed successfully!"
echo ""

# Step 10: Deploy test alert
info "Deploying test alert (always firing)..."
kubectl apply -f k8s/always-firing-rule.yaml || {
    warn "Could not deploy test alert. Check if file exists."
}

echo ""
echo "========================================"
echo "  Deployment Complete!"
echo "========================================"
echo ""

info "Verifying all pods..."
echo ""
kubectl get pods -n observability
echo ""
kubectl get pods -n monitoring | grep -E "(prometheus|alertmanager)"
echo ""

info "Checking Kafka consumer groups..."
kubectl exec -n observability kafka-0 -- \
    kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list 2>/dev/null || {
    warn "Could not list consumer groups"
}

echo ""
echo "========================================"
echo "  Access Services"
echo "========================================"
echo ""
echo "Neo4j Browser:"
echo "  kubectl port-forward -n observability svc/neo4j-external 7474:7474"
echo "  http://localhost:7474"
echo "  Username: neo4j"
echo "  Password: anuragvishwa"
echo ""
echo "Kafka UI:"
echo "  kubectl port-forward -n observability svc/kafka-ui 7777:8080"
echo "  http://localhost:7777"
echo ""
echo "Prometheus:"
echo "  kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090"
echo "  http://localhost:9090"
echo ""
echo "Alertmanager:"
echo "  kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-alertmanager 9093:9093"
echo "  http://localhost:9093"
echo ""
echo "========================================"
echo "  Next Steps"
echo "========================================"
echo ""
echo "1. Configure Alertmanager webhook to Vector:"
echo "   kubectl edit secret -n monitoring alertmanager-prometheus-kube-prometheus-alertmanager"
echo "   Add: webhook_configs: [{url: 'http://vector.observability.svc:9000'}]"
echo ""
echo "2. Access Neo4j and run RCA queries (see README.md)"
echo ""
echo "3. Check message flow:"
echo "   kubectl exec -n observability kafka-0 -- \\"
echo "     kafka-consumer-groups.sh --bootstrap-server localhost:9092 \\"
echo "     --group kg-builder --describe"
echo ""
echo "4. View logs:"
echo "   kubectl logs -n observability -l app=kg-builder -f"
echo "   kubectl logs -n observability -l app=vector -f"
echo "   kubectl logs -n observability -l app=state-watcher -f"
echo ""
echo "For detailed documentation, see README.md and KGROOT_RCA_IMPROVEMENTS.md"
echo ""
