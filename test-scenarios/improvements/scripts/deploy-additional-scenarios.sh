#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS_DIR="$SCRIPT_DIR/../scenarios"

echo "=========================================="
echo "Deploying Additional Test Scenarios"
echo "=========================================="
echo ""

echo "These scenarios cover additional K8s error types:"
echo "  - FailedScheduling (node selector, resources)"
echo "  - FailedMount (ConfigMap, PVC, Secret)"
echo "  - Invalid container configuration"
echo "  - Network errors"
echo "  - Resource pressure (CPU, disk)"
echo ""

read -p "Deploy additional scenarios? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo "1. Deploying FailedScheduling tests..."
kubectl apply -f "$SCENARIOS_DIR/failed-scheduling.yaml"

echo "2. Deploying FailedMount tests..."
kubectl apply -f "$SCENARIOS_DIR/failed-mount.yaml"

echo "3. Deploying invalid container config tests..."
kubectl apply -f "$SCENARIOS_DIR/invalid-container-config.yaml"

echo "4. Deploying network error tests..."
kubectl apply -f "$SCENARIOS_DIR/network-errors.yaml"

echo "5. Deploying resource pressure tests..."
kubectl apply -f "$SCENARIOS_DIR/resource-pressure.yaml"

echo ""
echo "✓ Additional scenarios deployed!"
echo ""

sleep 3

echo "=========================================="
echo "Current Pod Status"
echo "=========================================="
kubectl get pods -n kg-testing

echo ""
echo "=========================================="
echo "Expected Results:"
echo "=========================================="
echo "• failed-scheduling-*: Pending (FailedScheduling)"
echo "• failed-mount-*: ContainerCreating or Error"
echo "• invalid-*: Error or CrashLoopBackOff"
echo "• network-error-test: Running (but logging errors)"
echo "• cpu-throttle-test: Running (CPU throttled)"
echo "• disk-pressure-test: Running"
echo ""
echo "Monitor events:"
echo "  kubectl get events -n kg-testing --sort-by='.lastTimestamp' | tail -20"
echo ""
echo "Wait 2-3 minutes, then check Neo4j for new event types!"
