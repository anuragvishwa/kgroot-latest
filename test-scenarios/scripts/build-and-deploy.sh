#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Building Test Applications Docker Image"
echo "=========================================="

cd "$ROOT_DIR/apps"
docker build -t kg-test-apps:latest .
echo "✓ Docker image built: kg-test-apps:latest"

# Load into minikube if using minikube
if command -v minikube &> /dev/null && minikube status &> /dev/null; then
    echo ""
    echo "Loading image into Minikube..."
    minikube image load kg-test-apps:latest
    echo "✓ Image loaded into Minikube"
fi

echo ""
echo "=========================================="
echo "Deploying Test Scenarios to Kubernetes"
echo "=========================================="

# Create namespace
echo "Creating kg-testing namespace..."
kubectl apply -f "$ROOT_DIR/k8s/00-namespace.yaml"
echo "✓ Namespace created"

echo ""
echo "Deploying test applications..."
echo "  1. CrashLoop Test (will continuously crash)"
kubectl apply -f "$ROOT_DIR/k8s/01-crashloop.yaml"

echo "  2. OOM Killer Test (will be OOM killed)"
kubectl apply -f "$ROOT_DIR/k8s/02-oom-killer.yaml"

echo "  3. Slow Startup Test (readiness probe failures)"
kubectl apply -f "$ROOT_DIR/k8s/03-slow-startup.yaml"

echo "  4. Error Logger Test (generates error logs)"
kubectl apply -f "$ROOT_DIR/k8s/04-error-logger.yaml"

echo "  5. Intermittent Failure Test (random failures)"
kubectl apply -f "$ROOT_DIR/k8s/05-intermittent-fail.yaml"

echo "  6. Resource Quota & Limits"
kubectl apply -f "$ROOT_DIR/k8s/06-resource-quota.yaml"

echo "  7. Image Pull Fail Test (non-existent image)"
kubectl apply -f "$ROOT_DIR/apps/image-pull-fail.yaml"

echo ""
echo "✓ All test scenarios deployed!"
echo ""
echo "=========================================="
echo "Deployment Status"
echo "=========================================="

sleep 3
kubectl get pods -n kg-testing
echo ""

echo "=========================================="
echo "What to expect:"
echo "=========================================="
echo "• crashloop-test: Will show CrashLoopBackOff"
echo "• oom-test: Will be OOMKilled repeatedly"
echo "• slow-startup-test: Will take ~90s to become Ready"
echo "• error-logger-test: Will run but log errors"
echo "• intermittent-fail-test: Will eventually crash"
echo "• image-pull-fail: Will show ImagePullBackOff"
echo ""
echo "Monitor with:"
echo "  kubectl get pods -n kg-testing -w"
echo "  kubectl logs -n kg-testing <pod-name> -f"
echo ""
echo "View events:"
echo "  kubectl get events -n kg-testing --sort-by='.lastTimestamp'"
echo ""
echo "Wait 2-3 minutes, then run Neo4j queries:"
echo "  cd $ROOT_DIR/queries"
echo "  ./run-test-queries.sh"
