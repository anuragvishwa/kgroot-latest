#!/bin/bash
# ============================================================================
# Deploy KG RCA Client to af-4 Cluster
# ============================================================================

set -e

CONTEXT="af-4"
NAMESPACE="kgroot"
RELEASE_NAME="kg-rca-agent"

echo "=========================================="
echo "Deploying KG RCA Client to af-4 Cluster"
echo "=========================================="
echo ""

# Check if context exists
if ! kubectl config get-contexts "$CONTEXT" &>/dev/null; then
    echo "❌ Context '$CONTEXT' not found in kubectl config"
    echo "Available contexts:"
    kubectl config get-contexts -o name
    exit 1
fi

echo "✅ Using context: $CONTEXT"
echo ""

# Create namespace if it doesn't exist
kubectl --context "$CONTEXT" create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl --context "$CONTEXT" apply -f -
echo "✅ Namespace '$NAMESPACE' ready"
echo ""

# Check if values file exists
if [ ! -f "values.af-4.yaml" ]; then
    echo "❌ values.af-4.yaml not found!"
    echo "Please create this file with your af-4 cluster configuration"
    exit 1
fi

echo "📋 Using values from: values.af-4.yaml"
echo ""

# Build Helm chart
echo "🔨 Packaging Helm chart..."
cd helm-chart
helm package . -d ..
cd ..
echo "✅ Chart packaged"
echo ""

# Deploy or upgrade
echo "🚀 Deploying to cluster..."
if kubectl --context "$CONTEXT" get secret -n "$NAMESPACE" -l owner=helm,name="$RELEASE_NAME" &>/dev/null; then
    echo "Upgrading existing release..."
    helm upgrade "$RELEASE_NAME" \
        --kube-context "$CONTEXT" \
        --namespace "$NAMESPACE" \
        --values values.af-4.yaml \
        ./kg-rca-agent-*.tgz \
        --wait \
        --timeout 5m
else
    echo "Installing new release..."
    helm install "$RELEASE_NAME" \
        --kube-context "$CONTEXT" \
        --namespace "$NAMESPACE" \
        --values values.af-4.yaml \
        --create-namespace \
        ./kg-rca-agent-*.tgz \
        --wait \
        --timeout 5m
fi

echo ""
echo "✅ Deployment complete!"
echo ""

# Show deployment status
echo "=========================================="
echo "Deployment Status"
echo "=========================================="
echo ""

echo "Pods:"
kubectl --context "$CONTEXT" get pods -n "$NAMESPACE"
echo ""

echo "ConfigMap CLIENT_ID:"
kubectl --context "$CONTEXT" get configmap -n "$NAMESPACE" kg-rca-agent-config -o jsonpath='{.data.CLIENT_ID}'
echo ""
echo ""

echo "=========================================="
echo "Verification Commands"
echo "=========================================="
echo ""
echo "Check state-watcher logs:"
echo "  kubectl --context $CONTEXT logs -n $NAMESPACE -l component=state-watcher --tail=50"
echo ""
echo "Check event-exporter logs:"
echo "  kubectl --context $CONTEXT logs -n $NAMESPACE -l component=event-exporter --tail=50"
echo ""
echo "Check CLIENT_ID in pod:"
echo "  kubectl --context $CONTEXT exec -n $NAMESPACE -l component=state-watcher -- env | grep CLIENT_ID"
echo ""
