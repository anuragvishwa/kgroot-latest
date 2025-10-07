#!/bin/bash
# Neo4j Port-Forward Keep-Alive Script
# This script maintains a stable port-forward connection to Neo4j

set -e

NAMESPACE="observability"
POD_NAME="neo4j-0"
HTTP_PORT="7474"
BOLT_PORT="7687"
LOG_FILE="/tmp/neo4j-port-forward.log"

echo "=== Neo4j Port-Forward Keep-Alive ==="
echo "Namespace: $NAMESPACE"
echo "Pod: $POD_NAME"
echo "Ports: $HTTP_PORT (HTTP), $BOLT_PORT (Bolt)"
echo "Log: $LOG_FILE"
echo ""

# Kill any existing port-forwards
echo "Stopping existing port-forwards..."
pkill -f "kubectl port-forward.*neo4j" 2>/dev/null || true
sleep 2

# Check if pod exists and is running
echo "Checking if Neo4j pod is running..."
if ! kubectl get pod "$POD_NAME" -n "$NAMESPACE" &>/dev/null; then
    echo "ERROR: Pod $POD_NAME not found in namespace $NAMESPACE"
    exit 1
fi

POD_STATUS=$(kubectl get pod "$POD_NAME" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
if [ "$POD_STATUS" != "Running" ]; then
    echo "ERROR: Pod $POD_NAME is not running (status: $POD_STATUS)"
    exit 1
fi

echo "Pod is running. Starting port-forward..."
echo ""

# Function to start port-forward
start_port_forward() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting port-forward..."
    kubectl port-forward -n "$NAMESPACE" "pod/$POD_NAME" \
        "$HTTP_PORT:$HTTP_PORT" "$BOLT_PORT:$BOLT_PORT" \
        >> "$LOG_FILE" 2>&1 &
    PF_PID=$!
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port-forward started (PID: $PF_PID)"
    echo "$PF_PID" > /tmp/neo4j-pf.pid
}

# Function to check if port-forward is alive
check_port_forward() {
    if [ -f /tmp/neo4j-pf.pid ]; then
        PF_PID=$(cat /tmp/neo4j-pf.pid)
        if ps -p "$PF_PID" > /dev/null 2>&1; then
            return 0  # Still running
        fi
    fi
    return 1  # Not running
}

# Start initial port-forward
start_port_forward
sleep 3

# Verify connection
echo ""
echo "Verifying connection..."
if curl -s "http://localhost:$HTTP_PORT" | grep -q "bolt"; then
    echo "✓ HTTP connection successful"
else
    echo "✗ HTTP connection failed"
fi

echo ""
echo "=== Connection Details ==="
echo "Neo4j Browser:  http://localhost:7474/browser/"
echo "Bolt Protocol:  bolt://localhost:7687"
echo "Username:       neo4j"
echo "Password:       anuragvishwa"
echo ""
echo "Port-forward is running in background (PID: $PF_PID)"
echo "Log file: $LOG_FILE"
echo ""
echo "To stop:"
echo "  pkill -f 'kubectl port-forward.*neo4j'"
echo ""
echo "To monitor:"
echo "  tail -f $LOG_FILE"
echo ""

# Keep-alive loop (optional - runs in foreground if script is kept open)
if [ "${1:-}" = "--keep-alive" ]; then
    echo "Keep-alive mode enabled. Press Ctrl+C to stop."
    echo ""
    while true; do
        sleep 10
        if ! check_port_forward; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port-forward died. Restarting..."
            start_port_forward
            sleep 3
        fi
    done
fi
