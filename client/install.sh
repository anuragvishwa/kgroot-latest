#!/bin/bash
set -euo pipefail

# KGroot Client Installation Script
# Automates the installation of KGroot client to Kubernetes cluster

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl first."
        exit 1
    fi
    log_success "kubectl found: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

    # Check helm
    if ! command -v helm &> /dev/null; then
        log_error "helm not found. Please install Helm 3 first."
        exit 1
    fi
    log_success "helm found: $(helm version --short)"

    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Check your kubeconfig."
        exit 1
    fi
    log_success "Connected to cluster: $(kubectl config current-context)"
}

# Prompt for configuration
prompt_config() {
    echo ""
    log_info "=== KGroot Client Configuration ==="
    echo ""

    # Cluster name
    read -p "Enter cluster name (e.g., 'production', 'staging'): " CLUSTER_NAME
    if [ -z "$CLUSTER_NAME" ]; then
        log_error "Cluster name is required!"
        exit 1
    fi

    # Server endpoint
    read -p "Enter KGroot server Kafka endpoint (e.g., '54.123.45.67:9092'): " KAFKA_BROKERS
    if [ -z "$KAFKA_BROKERS" ]; then
        log_error "Kafka brokers endpoint is required!"
        exit 1
    fi

    # Test connectivity
    log_info "Testing connectivity to Kafka..."
    SERVER_IP=$(echo $KAFKA_BROKERS | cut -d: -f1)
    SERVER_PORT=$(echo $KAFKA_BROKERS | cut -d: -f2)

    if kubectl run kgroot-test --rm -i --image=busybox --restart=Never -- nc -zv $SERVER_IP $SERVER_PORT 2>&1 | grep -q "open\|succeeded"; then
        log_success "Connectivity test passed!"
    else
        log_warn "Could not verify connectivity to $KAFKA_BROKERS"
        read -p "Continue anyway? (y/N): " CONTINUE
        if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
            log_info "Installation cancelled."
            exit 0
        fi
    fi

    # Authentication
    echo ""
    read -p "Does your server require authentication? (y/N): " USE_AUTH
    if [ "$USE_AUTH" = "y" ] || [ "$USE_AUTH" = "Y" ]; then
        read -p "Enter SASL username: " SASL_USER
        read -sp "Enter SASL password: " SASL_PASS
        echo ""
        USE_SASL=true
    else
        USE_SASL=false
    fi

    # Namespace
    read -p "Enter namespace for installation (default: kgroot-client): " NAMESPACE
    NAMESPACE=${NAMESPACE:-kgroot-client}
}

# Install
install_client() {
    log_info "Installing KGroot client..."

    # Build helm command
    HELM_CMD="helm install kgroot-client ./helm-chart/kg-client"
    HELM_CMD="$HELM_CMD --set global.clusterName=$CLUSTER_NAME"
    HELM_CMD="$HELM_CMD --set server.kafka.brokers=$KAFKA_BROKERS"
    HELM_CMD="$HELM_CMD --namespace $NAMESPACE"
    HELM_CMD="$HELM_CMD --create-namespace"

    if [ "$USE_SASL" = true ]; then
        HELM_CMD="$HELM_CMD --set server.kafka.sasl.enabled=true"
        HELM_CMD="$HELM_CMD --set server.kafka.sasl.username=$SASL_USER"
        HELM_CMD="$HELM_CMD --set server.kafka.sasl.password=$SASL_PASS"
    fi

    # Execute
    log_info "Running: helm install kgroot-client..."
    if eval $HELM_CMD; then
        log_success "Helm chart installed successfully!"
    else
        log_error "Helm installation failed!"
        exit 1
    fi
}

# Wait for pods
wait_for_pods() {
    log_info "Waiting for pods to be ready (timeout: 120s)..."

    if kubectl wait --for=condition=ready pod \
        -l app.kubernetes.io/name=kg-client \
        -n $NAMESPACE \
        --timeout=120s &> /dev/null; then
        log_success "All pods are ready!"
    else
        log_warn "Some pods are not ready yet. Check status with:"
        echo "  kubectl get pods -n $NAMESPACE"
    fi
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    echo ""

    # List pods
    log_info "Deployed pods:"
    kubectl get pods -n $NAMESPACE
    echo ""

    # Check event exporter logs
    log_info "Event exporter logs (last 5 lines):"
    kubectl logs -n $NAMESPACE deployment/kgroot-client-event-exporter --tail 5 2>/dev/null || log_warn "Could not fetch logs"
    echo ""
}

# Print next steps
print_next_steps() {
    echo ""
    log_success "=== Installation Complete! ==="
    echo ""
    log_info "Next steps:"
    echo ""
    echo "1. Check pod status:"
    echo "   kubectl get pods -n $NAMESPACE"
    echo ""
    echo "2. View logs:"
    echo "   kubectl logs -n $NAMESPACE deployment/kgroot-client-event-exporter -f"
    echo "   kubectl logs -n $NAMESPACE ds/kgroot-client-vector -f"
    echo ""
    echo "3. Generate test event:"
    echo "   kubectl run test-crash --image=busybox --restart=Never -- /bin/sh -c 'exit 1'"
    echo ""
    echo "4. Verify on server:"
    echo "   ssh your-server 'docker exec kgroot-latest-kafka-1 kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list'"
    echo ""
    echo "5. Query the knowledge graph:"
    echo "   See: /validation/interactive-query-test.sh"
    echo ""
    log_info "For more info, see: client/README.md"
}

# Main
main() {
    echo ""
    log_info "=== KGroot Client Installer ==="
    echo ""

    # Check we're in the right directory
    if [ ! -d "helm-chart/kg-client" ]; then
        log_error "helm-chart/kg-client directory not found!"
        log_error "Please run this script from the 'client' directory."
        exit 1
    fi

    check_prerequisites
    prompt_config

    echo ""
    log_info "Configuration summary:"
    echo "  Cluster Name: $CLUSTER_NAME"
    echo "  Kafka Brokers: $KAFKA_BROKERS"
    echo "  Namespace: $NAMESPACE"
    echo "  Authentication: $([ "$USE_SASL" = true ] && echo "Enabled" || echo "Disabled")"
    echo ""

    read -p "Proceed with installation? (Y/n): " PROCEED
    if [ "$PROCEED" = "n" ] || [ "$PROCEED" = "N" ]; then
        log_info "Installation cancelled."
        exit 0
    fi

    install_client
    wait_for_pods
    verify_installation
    print_next_steps
}

# Run
main
