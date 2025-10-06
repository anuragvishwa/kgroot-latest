#!/bin/bash
set -e

echo "Building alerts-enricher Docker image..."
docker build -t alerts-enricher:latest .

echo "Loading image into Minikube..."
minikube image load alerts-enricher:latest

echo "Restarting deployment..."
kubectl rollout restart deployment/alerts-enricher -n observability

echo "Waiting for deployment to be ready..."
kubectl wait --for=condition=available deployment/alerts-enricher -n observability --timeout=120s

echo "✅ Alerts enricher deployed successfully!"
echo ""
echo "Check logs with:"
echo "  kubectl logs -n observability deployment/alerts-enricher -f"
