#!/bin/bash

# Test script to validate Helm chart before release

set -e

echo "=========================================="
echo "KG RCA Agent - Installation Test"
echo "=========================================="

# Check prerequisites
echo -e "\n[1/6] Checking prerequisites..."

if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl."
    exit 1
fi
echo "✓ kubectl found"

if ! command -v helm &> /dev/null; then
    echo "❌ helm not found. Please install Helm 3.x."
    exit 1
fi
echo "✓ helm found"

# Check kubectl access
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ kubectl cannot access cluster. Check your kubeconfig."
    exit 1
fi
echo "✓ kubectl can access cluster"

# Validate Helm chart
echo -e "\n[2/6] Validating Helm chart..."
if ! helm lint helm-chart/kg-rca-agent; then
    echo "❌ Helm chart validation failed"
    exit 1
fi
echo "✓ Helm chart is valid"

# Check if example values file exists
echo -e "\n[3/6] Checking configuration..."
if [ ! -f "example-values.yaml" ]; then
    echo "❌ example-values.yaml not found"
    exit 1
fi
echo "✓ example-values.yaml found"

# Dry-run installation
echo -e "\n[4/6] Testing dry-run installation..."
if ! helm install kg-rca-agent-test helm-chart/kg-rca-agent \
    --values example-values.yaml \
    --namespace observability \
    --dry-run --debug > /dev/null; then
    echo "❌ Dry-run installation failed"
    exit 1
fi
echo "✓ Dry-run successful"

# Template rendering test
echo -e "\n[5/6] Testing template rendering..."
helm template kg-rca-agent helm-chart/kg-rca-agent \
    --values example-values.yaml \
    --namespace observability > /tmp/kg-rca-rendered.yaml

if [ ! -s /tmp/kg-rca-rendered.yaml ]; then
    echo "❌ Template rendering produced empty output"
    exit 1
fi

# Check for required resources
REQUIRED_RESOURCES=("DaemonSet" "Deployment" "ConfigMap" "ServiceAccount" "ClusterRole")
for resource in "${REQUIRED_RESOURCES[@]}"; do
    if ! grep -q "kind: $resource" /tmp/kg-rca-rendered.yaml; then
        echo "❌ Missing required resource: $resource"
        exit 1
    fi
done
echo "✓ All required Kubernetes resources present"

# Summary
echo -e "\n[6/6] Validation Summary"
echo "=========================================="
echo "✓ Prerequisites installed"
echo "✓ Cluster accessible"
echo "✓ Helm chart valid"
echo "✓ Configuration files present"
echo "✓ Templates render correctly"
echo "✓ All required resources defined"
echo "=========================================="
echo ""
echo "✅ Chart is ready for installation!"
echo ""
echo "To install on your cluster:"
echo "  1. Copy example-values.yaml to my-values.yaml"
echo "  2. Edit my-values.yaml with your server details"
echo "  3. Run: helm install kg-rca-agent helm-chart/kg-rca-agent \\"
echo "          --values my-values.yaml \\"
echo "          --namespace observability \\"
echo "          --create-namespace"
echo ""
