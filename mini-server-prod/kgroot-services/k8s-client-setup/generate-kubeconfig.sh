#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════
# KGroot RCA - Generate Read-Only Kubeconfig
# ═══════════════════════════════════════════════════════════════════════════
#
# This script generates a kubeconfig file with read-only access for external
# RCA monitoring. It should be run by the CLIENT who owns the K8s cluster.
#
# Prerequisites:
# 1. kubectl configured and connected to your cluster
# 2. rbac-readonly.yaml already applied
#
# Usage:
#   ./generate-kubeconfig.sh
#
# Output:
#   kgroot-readonly-kubeconfig.yaml (send this file to RCA team)
# ═══════════════════════════════════════════════════════════════════════════

set -e

NAMESPACE="kgroot-monitoring"
SERVICE_ACCOUNT="kgroot-readonly"
SECRET_NAME="kgroot-readonly-token"
OUTPUT_FILE="kgroot-readonly-kubeconfig.yaml"

echo "════════════════════════════════════════════════════════════════"
echo "KGroot RCA - Kubeconfig Generator"
echo "════════════════════════════════════════════════════════════════"
echo ""

# ─────────────────────────────────────────────────────────────────────────
# Step 1: Verify RBAC is applied
# ─────────────────────────────────────────────────────────────────────────
echo "✓ Checking if RBAC is applied..."
if ! kubectl get namespace $NAMESPACE &>/dev/null; then
    echo "❌ Namespace $NAMESPACE not found!"
    echo "   Please apply rbac-readonly.yaml first:"
    echo "   kubectl apply -f rbac-readonly.yaml"
    exit 1
fi

if ! kubectl get serviceaccount $SERVICE_ACCOUNT -n $NAMESPACE &>/dev/null; then
    echo "❌ ServiceAccount $SERVICE_ACCOUNT not found!"
    echo "   Please apply rbac-readonly.yaml first:"
    echo "   kubectl apply -f rbac-readonly.yaml"
    exit 1
fi

echo "✓ RBAC configuration found"
echo ""

# ─────────────────────────────────────────────────────────────────────────
# Step 2: Get cluster info
# ─────────────────────────────────────────────────────────────────────────
echo "✓ Extracting cluster information..."

CLUSTER_NAME=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}')
CLUSTER_SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CLUSTER_CA=$(kubectl get secret $SECRET_NAME -n $NAMESPACE -o jsonpath='{.data.ca\.crt}')

echo "  Cluster: $CLUSTER_NAME"
echo "  Server: $CLUSTER_SERVER"
echo ""

# ─────────────────────────────────────────────────────────────────────────
# Step 3: Get service account token
# ─────────────────────────────────────────────────────────────────────────
echo "✓ Extracting service account token..."

# Wait for token to be created (may take a few seconds)
for i in {1..10}; do
    TOKEN=$(kubectl get secret $SECRET_NAME -n $NAMESPACE -o jsonpath='{.data.token}' 2>/dev/null || echo "")
    if [ -n "$TOKEN" ]; then
        break
    fi
    echo "  Waiting for token creation... ($i/10)"
    sleep 2
done

if [ -z "$TOKEN" ]; then
    echo "❌ Failed to get token from secret $SECRET_NAME"
    echo "   The secret may not have been created yet."
    echo "   Try running: kubectl delete secret $SECRET_NAME -n $NAMESPACE"
    echo "   Then re-apply rbac-readonly.yaml"
    exit 1
fi

echo "✓ Token extracted successfully"
echo ""

# ─────────────────────────────────────────────────────────────────────────
# Step 4: Generate kubeconfig
# ─────────────────────────────────────────────────────────────────────────
echo "✓ Generating kubeconfig file..."

cat > $OUTPUT_FILE <<EOF
apiVersion: v1
kind: Config
clusters:
- name: $CLUSTER_NAME
  cluster:
    certificate-authority-data: $CLUSTER_CA
    server: $CLUSTER_SERVER
contexts:
- name: kgroot-readonly@$CLUSTER_NAME
  context:
    cluster: $CLUSTER_NAME
    user: kgroot-readonly
    namespace: default
current-context: kgroot-readonly@$CLUSTER_NAME
users:
- name: kgroot-readonly
  user:
    token: $(echo $TOKEN | base64 -d)
EOF

echo "✓ Kubeconfig generated successfully!"
echo ""

# ─────────────────────────────────────────────────────────────────────────
# Step 5: Verify access
# ─────────────────────────────────────────────────────────────────────────
echo "✓ Verifying read-only access..."

if kubectl --kubeconfig=$OUTPUT_FILE get nodes &>/dev/null; then
    echo "✓ Successfully verified read access to nodes"
else
    echo "⚠️  Warning: Could not verify access. The kubeconfig may still work."
fi

if kubectl --kubeconfig=$OUTPUT_FILE get events --all-namespaces --limit=1 &>/dev/null; then
    echo "✓ Successfully verified read access to events"
else
    echo "⚠️  Warning: Could not verify access to events"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "SUCCESS! Kubeconfig file created: $OUTPUT_FILE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📄 File details:"
ls -lh $OUTPUT_FILE
echo ""
echo "🔐 Security Information:"
echo "   • This kubeconfig has READ-ONLY access"
echo "   • It can view events, pods, nodes, deployments, services"
echo "   • It CANNOT create, modify, or delete any resources"
echo "   • Token is cluster-scoped but has minimal permissions"
echo ""
echo "📤 Next Steps:"
echo "   1. Review the file to ensure no sensitive info"
echo "   2. Send $OUTPUT_FILE to the RCA team securely"
echo "   3. Recommended: Use encrypted file transfer or secrets manager"
echo ""
echo "🔄 To revoke access later:"
echo "   kubectl delete clusterrolebinding kgroot-readonly-binding"
echo "   kubectl delete namespace $NAMESPACE"
echo ""
