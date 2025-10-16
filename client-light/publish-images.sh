#!/bin/bash
set -e

# Configuration
DOCKER_USER="anuragvishwa"
VERSION="1.0.2"

echo "=============================================="
echo "Publishing KG RCA Agent Images to Docker Hub"
echo "=============================================="
echo "Docker Hub user: $DOCKER_USER"
echo "Version: $VERSION"
echo ""

# Check if logged in to Docker Hub
echo "Checking Docker Hub authentication..."
echo "✓ Proceeding with Docker Hub push (will fail if not authenticated)"
echo ""

# Build and push alert-receiver
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1/2 Building and pushing alert-receiver..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd ../alerts-enricher

echo "Building image..."
docker build -t $DOCKER_USER/kg-alert-receiver:$VERSION \
             -t $DOCKER_USER/kg-alert-receiver:latest .

echo "Pushing to Docker Hub..."
docker push $DOCKER_USER/kg-alert-receiver:$VERSION
docker push $DOCKER_USER/kg-alert-receiver:latest
echo "✓ $DOCKER_USER/kg-alert-receiver:$VERSION published"
echo ""

# Build and push state-watcher
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2/2 Building and pushing state-watcher..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd ../state-watcher

echo "Building image..."
docker build -t $DOCKER_USER/kg-state-watcher:$VERSION \
             -t $DOCKER_USER/kg-state-watcher:latest .

echo "Pushing to Docker Hub..."
docker push $DOCKER_USER/kg-state-watcher:$VERSION
docker push $DOCKER_USER/kg-state-watcher:latest
echo "✓ $DOCKER_USER/kg-state-watcher:$VERSION published"
echo ""

echo "=============================================="
echo "✓ All images published successfully!"
echo "=============================================="
echo ""
echo "Published images:"
echo "  • docker.io/$DOCKER_USER/kg-alert-receiver:$VERSION"
echo "  • docker.io/$DOCKER_USER/kg-alert-receiver:latest"
echo "  • docker.io/$DOCKER_USER/kg-state-watcher:$VERSION"
echo "  • docker.io/$DOCKER_USER/kg-state-watcher:latest"
echo ""
echo "View on Docker Hub:"
echo "  https://hub.docker.com/r/$DOCKER_USER/kg-alert-receiver"
echo "  https://hub.docker.com/r/$DOCKER_USER/kg-state-watcher"
echo ""
echo "Next steps:"
echo "1. Update Helm chart values.yaml with these image references"
echo "2. Update Chart.yaml annotations with image list"
echo "3. Package and publish new Helm chart version"
