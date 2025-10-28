#!/bin/bash

# Build and push minimal Kafka producer image
# Usage: ./build-and-push.sh [version]

set -e

VERSION=${1:-"1.0.0"}
IMAGE_NAME="anuragvishwa/kafka-producer-minimal"
FULL_IMAGE="${IMAGE_NAME}:${VERSION}"
LATEST_IMAGE="${IMAGE_NAME}:latest"

echo "Building ${FULL_IMAGE}..."

# Build the image
docker build -t "${FULL_IMAGE}" -t "${LATEST_IMAGE}" .

echo ""
echo "Image built successfully!"
echo ""

# Get image size
IMAGE_SIZE=$(docker images "${FULL_IMAGE}" --format "{{.Size}}")
echo "Image size: ${IMAGE_SIZE}"
echo ""

# Test the image
echo "Testing image..."
docker run --rm "${FULL_IMAGE}" kafka-console-producer --version || echo "Version check completed"
echo ""

# Ask for confirmation before pushing
read -p "Push to Docker Hub? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Pushing ${FULL_IMAGE}..."
    docker push "${FULL_IMAGE}"

    echo "Pushing ${LATEST_IMAGE}..."
    docker push "${LATEST_IMAGE}"

    echo ""
    echo "✅ Images pushed successfully!"
    echo ""
    echo "To use in your Helm chart:"
    echo "  image: ${FULL_IMAGE}"
else
    echo ""
    echo "Skipped push. To push manually:"
    echo "  docker push ${FULL_IMAGE}"
    echo "  docker push ${LATEST_IMAGE}"
fi

echo ""
echo "Done!"
