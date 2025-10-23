#!/bin/bash

set -e

VERSION=${1:-1.0.16}
IMAGE_NAME="anuragvishwa/kg-alert-receiver"

echo "Building alert-receiver version ${VERSION}..."

# Build Docker image
docker build -t ${IMAGE_NAME}:${VERSION} .
docker tag ${IMAGE_NAME}:${VERSION} ${IMAGE_NAME}:latest

echo "Pushing to Docker Hub..."
docker push ${IMAGE_NAME}:${VERSION}
docker push ${IMAGE_NAME}:latest

echo "✅ Successfully built and pushed ${IMAGE_NAME}:${VERSION}"
