#!/bin/bash
set -e

echo "=========================================="
echo "Cleaning Up Test Scenarios"
echo "=========================================="

echo "Deleting all resources in kg-testing namespace..."
kubectl delete namespace kg-testing --ignore-not-found=true

echo ""
echo "✓ Cleanup complete!"
echo ""
echo "Note: Events and logs may still be in Neo4j knowledge graph."
echo "To query historical test data, use the Neo4j queries in ./queries/"
