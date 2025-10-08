#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "Production-Level Test Deployment"
echo "=========================================="
echo ""

echo "This will deploy:"
echo "  ✅ Prometheus alert scenarios"
echo "  ✅ StatefulSet tests"
echo "  ✅ DaemonSet tests"
echo "  ✅ Job/CronJob tests"
echo "  ✅ HPA scaling tests"
echo "  ✅ Additional failure scenarios"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "1. Deploying Prometheus Alert Rules..."
kubectl apply -f "$SCRIPT_DIR/prometheus-alerts.yaml" || echo "⚠️  Prometheus rules may need Prometheus Operator"

echo ""
echo "2. Deploying StatefulSet tests..."
kubectl apply -f "$SCRIPT_DIR/statefulset-tests.yaml"

echo ""
echo "3. Deploying DaemonSet tests..."
kubectl apply -f "$SCRIPT_DIR/daemonset-tests.yaml"

echo ""
echo "4. Deploying Job/CronJob tests..."
kubectl apply -f "$SCRIPT_DIR/job-cronjob-tests.yaml"

echo ""
echo "5. Deploying HPA scaling tests..."
kubectl apply -f "$SCRIPT_DIR/hpa-scaling-tests.yaml"

echo ""
echo "6. Deploying additional failure scenarios (fixed)..."
kubectl apply -f "$SCRIPT_DIR/../improvements/scenarios/failed-scheduling.yaml" || echo "Some pods expected to fail scheduling"
kubectl apply -f "$SCRIPT_DIR/../improvements/scenarios/failed-mount.yaml" || echo "Some pods expected to fail mounting"
kubectl apply -f "$SCRIPT_DIR/../improvements/scenarios/invalid-container-config.yaml" || echo "Some pods expected to fail startup"
kubectl apply -f "$SCRIPT_DIR/../improvements/scenarios/network-errors.yaml"
kubectl apply -f "$SCRIPT_DIR/../improvements/scenarios/resource-pressure.yaml"

echo ""
echo "✅ All production tests deployed!"
echo ""

sleep 3

echo "=========================================="
echo "Current Status"
echo "=========================================="
kubectl get all -n kg-testing

echo ""
echo "=========================================="
echo "Monitoring Commands"
echo "=========================================="
echo ""
echo "Watch pods:"
echo "  kubectl get pods -n kg-testing -w"
echo ""
echo "Watch events:"
echo "  kubectl get events -n kg-testing --sort-by='.lastTimestamp' --watch"
echo ""
echo "Check Kafka topics:"
echo "  cd ../improvements/scripts && ./check-kafka-topics.sh"
echo ""
echo "Validate RCA (wait 5 minutes):"
echo "  docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa"
echo '  "MATCH ()-[r:POTENTIAL_CAUSE]->() RETURN count(r);"'
echo ""
echo "Run full validation:"
echo "  docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa < rca-validation-queries.cypher"
echo ""

echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""
echo "1. Wait 5-10 minutes for events to flow"
echo "2. Check Kafka UI: http://localhost:7777"
echo "3. Check Neo4j: http://localhost:7474"
echo "4. Run validation queries from rca-validation-queries.cypher"
echo "5. Follow PRE_PRODUCTION_TEST_PLAN.md for full test suite"
echo ""
echo "Expected Results:"
echo "  • 50+ pods running (various states)"
echo "  • 20+ event types captured"
echo "  • 20,000+ RCA links (you already have 19,928!)"
echo "  • StatefulSet, DaemonSet, Job events"
echo "  • Prometheus alerts firing"
echo ""
