#!/usr/bin/env bash
set -euo pipefail

echo "=== Building kg-builder ==="

# Navigate to kg directory
cd "$(dirname "$0")"

# Generate go.sum if it doesn't exist
if [ ! -f go.sum ]; then
  echo "Generating go.sum..."
  go mod download
  go mod tidy
fi

# Build Docker image
echo "Building Docker image..."
docker build -t anuragvishwa/kg-builder:latest .

# Load into Minikube
echo "Loading image into Minikube..."
minikube image load anuragvishwa/kg-builder:latest

echo "=== Build complete ==="
echo ""
echo "To deploy, run:"
echo "  kubectl apply -f ../k8s/neo4j.yaml"
echo "  kubectl apply -f ../k8s/kg-builder.yaml"
echo ""
echo "To verify:"
echo "  kubectl get pods -n observability | grep -E '(neo4j|kg-builder)'"
echo "  kubectl logs -n observability -l app=kg-builder -f"
