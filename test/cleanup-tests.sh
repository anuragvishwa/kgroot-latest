#!/usr/bin/env bash
set -euo pipefail

echo "Cleaning up RCA test scenarios..."
echo ""

# Delete all test deployments and services
kubectl delete deployment,service -l test=rca-imagepull --ignore-not-found=true
kubectl delete deployment,service -l test=rca-crashloop --ignore-not-found=true
kubectl delete deployment -l test=rca-oom --ignore-not-found=true
kubectl delete deployment,service -l test=rca-service --ignore-not-found=true
kubectl delete deployment,service -l test=rca-cascade --ignore-not-found=true
kubectl delete deployment -l test=rca-config --ignore-not-found=true

# Delete by specific names (in case labels don't match)
kubectl delete deployment test-imagepull test-crashloop test-oom test-backend test-db test-api test-frontend test-missing-env --ignore-not-found=true
kubectl delete service test-imagepull test-crashloop test-backend test-db test-api test-frontend --ignore-not-found=true

echo ""
echo "✅ All test scenarios removed."
echo ""
echo "To verify:"
echo "  kubectl get pods -l test"
echo "  (should return: No resources found)"
echo ""
echo "Note: Events and logs are still in Neo4j for analysis."
echo "To clear Neo4j graph:"
echo "  kubectl exec -n observability neo4j-0 -- cypher-shell -u neo4j -p anuragvishwa 'MATCH (n) DETACH DELETE n;'"
