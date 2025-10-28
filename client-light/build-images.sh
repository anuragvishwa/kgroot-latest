#!/bin/bash
set -e

echo "========================================="
echo "Building KG RCA Agent Images for Minikube"
echo "========================================="

# Use minikube's docker daemon
echo "Configuring to use Minikube's Docker daemon..."
eval $(minikube -p minikube docker-env)

# Build alert-receiver (from alerts-enricher)
echo ""
echo "1/2 Building kg-rca/alert-receiver:latest..."
cd ../alerts-enricher
docker build -t kg-rca/alert-receiver:latest .
echo "✓ kg-rca/alert-receiver:latest built successfully"

# Build state-watcher
echo ""
echo "2/2 Building kg-rca/state-watcher:latest..."
cd ../state-watcher
docker build -t kg-rca/state-watcher:latest .
echo "✓ kg-rca/state-watcher:latest built successfully"

echo ""
echo "========================================="
echo "✓ All images built successfully!"
echo "========================================="
echo ""
echo "Images are now available in Minikube:"
docker images | grep -E "REPOSITORY|kg-rca"

echo ""
echo "Next steps:"
echo "1. Update your values file with the correct Kafka broker and client ID"
echo "2. Install/upgrade the Helm chart:"
echo "   helm upgrade --install kg-rca-agent ./helm-chart \\"
echo "     --values my-values.yaml \\"
echo "     --namespace observability \\"
echo "     --create-namespace"
