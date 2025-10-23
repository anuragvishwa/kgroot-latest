#!/bin/bash
set -e

VERSION="1.0.0"
IMAGE="anuragvishwa/kg-control-plane"

echo "🔨 Building control-plane:${VERSION}..."

# Build multi-arch image
docker buildx build --platform linux/amd64,linux/arm64 \
  -t ${IMAGE}:${VERSION} \
  -t ${IMAGE}:latest \
  --push .

echo "✅ Built and pushed ${IMAGE}:${VERSION}"
echo "✅ Built and pushed ${IMAGE}:latest"
