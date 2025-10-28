#!/bin/bash
# Fix zstd compression codec error in control plane

set -e

echo "🔧 Fixing zstd compression codec error..."
echo ""

cd /Users/anuragvishwa/Anurag/kgroot_latest/mini-server-prod

# Stop control plane
echo "⏹️  Stopping kg-control-plane..."
docker stop kg-control-plane || true
docker rm kg-control-plane || true

# Rebuild control plane image with zstandard
echo "🔨 Rebuilding control plane image with zstd support..."
cd kgroot-services
docker build -t anuragvishwa/kg-control-plane:2.0.0 -f Dockerfile --no-cache .

echo "✅ Image rebuilt with zstandard==0.22.0"
echo ""

# Restart control plane
cd ..
echo "🚀 Restarting control plane..."
docker-compose -f docker-compose-control-plane.yml up -d kg-control-plane

echo ""
echo "⏳ Waiting 5 seconds for startup..."
sleep 5

echo ""
echo "📋 Control plane logs:"
docker logs kg-control-plane --tail 20

echo ""
echo "✅ Control plane restarted successfully!"
echo ""
echo "Monitor logs with:"
echo "  docker logs kg-control-plane -f"
