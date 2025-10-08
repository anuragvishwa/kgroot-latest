#!/bin/bash

echo "Watching Kubernetes events in kg-testing namespace..."
echo "Press Ctrl+C to stop"
echo ""

kubectl get events -n kg-testing --watch --sort-by='.lastTimestamp'
