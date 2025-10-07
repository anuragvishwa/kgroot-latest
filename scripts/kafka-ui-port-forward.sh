#!/bin/bash
# Kafka UI Port-Forward Keep-Alive Script

set -e

NAMESPACE="observability"
SERVICE_NAME="kafka-ui"
LOCAL_PORT="8080"
REMOTE_PORT="8080"
LOG_FILE="/tmp/kafka-ui-port-forward.log"

echo "=== Kafka UI Port-Forward Keep-Alive ==="
echo "Namespace: $NAMESPACE"
echo "Service: $SERVICE_NAME"
echo "Local Port: $LOCAL_PORT"
echo "Log: $LOG_FILE"
echo ""

# Kill any existing port-forwards
echo "Stopping existing port-forwards..."
pkill -f "kubectl port-forward.*kafka-ui" 2>/dev/null || true
sleep 2

# Check if service exists
echo "Checking if Kafka UI service exists..."
if ! kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" &>/dev/null; then
    echo "ERROR: Service $SERVICE_NAME not found in namespace $NAMESPACE"
    exit 1
fi

echo "Service found. Starting port-forward..."
echo ""

# Start port-forward
kubectl port-forward -n "$NAMESPACE" "svc/$SERVICE_NAME" \
    "$LOCAL_PORT:$REMOTE_PORT" \
    >> "$LOG_FILE" 2>&1 &
PF_PID=$!
sleep 3

# Verify connection
echo "Verifying connection..."
if curl -s "http://localhost:$LOCAL_PORT" | grep -q "html"; then
    echo "✓ Kafka UI accessible"
else
    echo "✗ Connection verification failed (may still work)"
fi

echo ""
echo "=== Connection Details ==="
echo "Kafka UI:  http://localhost:$LOCAL_PORT"
echo ""
echo "Port-forward is running in background (PID: $PF_PID)"
echo "Log file: $LOG_FILE"
echo ""
echo "To stop:"
echo "  pkill -f 'kubectl port-forward.*kafka-ui'"
echo ""
