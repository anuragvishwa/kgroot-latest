# Client K8s Read-Only Access Setup Guide

## Overview
This guide helps you request and configure secure read-only access to your client's Kubernetes cluster for RCA monitoring.

## What to Request from Client

### Email Template for Client Request

```
Subject: Read-Only Kubernetes Access Request for RCA System

Dear [Client Name],

To enable our Root Cause Analysis (RCA) system to monitor and diagnose issues in your Kubernetes cluster, we need read-only access with the following permissions:

**What We Need Access To:**
- Pod status, logs, and events
- Deployment and service configurations
- Resource metrics (CPU, memory)
- Cluster events

**What We CANNOT Do:**
- Modify any resources
- Delete anything
- Create new workloads
- Access secrets or sensitive data
- Execute commands in pods

**Security Measures:**
- Service account with ClusterRole (read-only)
- Token-based authentication (no password)
- Can be revoked instantly by you
- All access is audited in K8s audit logs
- Token can have expiration time

**Setup Options:**

Option 1: You apply our RBAC manifests (most secure)
Option 2: We provide a script you run in your cluster
Option 3: We can do a screenshare where you apply the configs

Please find attached:
1. k8s-rbac-readonly.yaml - RBAC configuration
2. security-audit.md - Security review document

Can we schedule a call to discuss and implement this?

Best regards,
[Your Name]
```

## Setup Files for Client

### 1. RBAC Configuration
```yaml
# k8s-rbac-readonly.yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: kgroot-monitoring

---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kgroot-readonly-sa
  namespace: kgroot-monitoring

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kgroot-readonly-cluster-role
rules:
  # Read pods and pod logs
  - apiGroups: [""]
    resources:
      - pods
      - pods/log
      - pods/status
    verbs: ["get", "list", "watch"]

  # Read services and endpoints
  - apiGroups: [""]
    resources:
      - services
      - endpoints
    verbs: ["get", "list", "watch"]

  # Read deployments, replicasets, statefulsets
  - apiGroups: ["apps"]
    resources:
      - deployments
      - replicasets
      - statefulsets
      - daemonsets
    verbs: ["get", "list", "watch"]

  # Read nodes (for resource info)
  - apiGroups: [""]
    resources:
      - nodes
    verbs: ["get", "list", "watch"]

  # Read events (critical for RCA)
  - apiGroups: [""]
    resources:
      - events
    verbs: ["get", "list", "watch"]

  # Read metrics
  - apiGroups: ["metrics.k8s.io"]
    resources:
      - pods
      - nodes
    verbs: ["get", "list"]

  # Read ingresses (for routing info)
  - apiGroups: ["networking.k8s.io"]
    resources:
      - ingresses
    verbs: ["get", "list", "watch"]

  # Read HPA (horizontal pod autoscalers)
  - apiGroups: ["autoscaling"]
    resources:
      - horizontalpodautoscalers
    verbs: ["get", "list", "watch"]

  # IMPORTANT: NO write permissions
  # NO access to secrets
  # NO exec permissions

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kgroot-readonly-cluster-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kgroot-readonly-cluster-role
subjects:
  - kind: ServiceAccount
    name: kgroot-readonly-sa
    namespace: kgroot-monitoring

---
# Create long-lived token (K8s 1.24+)
apiVersion: v1
kind: Secret
metadata:
  name: kgroot-readonly-token
  namespace: kgroot-monitoring
  annotations:
    kubernetes.io/service-account.name: kgroot-readonly-sa
type: kubernetes.io/service-account-token
```

### 2. Setup Script for Client
```bash
#!/bin/bash
# setup-kgroot-access.sh
# This script creates read-only access for KGroot RCA system

set -e

echo "==================================="
echo "KGroot Read-Only Access Setup"
echo "==================================="

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if user has admin access
if ! kubectl auth can-i create clusterrole &> /dev/null; then
    echo "Error: You need cluster admin permissions to run this script."
    exit 1
fi

# Apply RBAC configuration
echo "Creating namespace and RBAC configuration..."
kubectl apply -f k8s-rbac-readonly.yaml

# Wait for service account to be created
echo "Waiting for service account creation..."
sleep 3

# Extract token
echo "Extracting access token..."
TOKEN=$(kubectl get secret kgroot-readonly-token -n kgroot-monitoring -o jsonpath='{.data.token}' | base64 -d)

if [ -z "$TOKEN" ]; then
    echo "Error: Failed to extract token"
    exit 1
fi

# Get cluster info
CLUSTER_URL=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CLUSTER_NAME=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}')
CA_CERT=$(kubectl get secret kgroot-readonly-token -n kgroot-monitoring -o jsonpath='{.data.ca\.crt}')

# Create kubeconfig
echo "Generating kubeconfig..."
cat > kgroot-kubeconfig.yaml <<EOF
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: ${CA_CERT}
    server: ${CLUSTER_URL}
  name: ${CLUSTER_NAME}
contexts:
- context:
    cluster: ${CLUSTER_NAME}
    user: kgroot-readonly
    namespace: kgroot-monitoring
  name: kgroot-context
current-context: kgroot-context
users:
- name: kgroot-readonly
  user:
    token: ${TOKEN}
EOF

echo ""
echo "==================================="
echo "Setup completed successfully!"
echo "==================================="
echo ""
echo "Generated file: kgroot-kubeconfig.yaml"
echo ""
echo "Next steps:"
echo "1. Test the access: kubectl --kubeconfig=kgroot-kubeconfig.yaml get pods -A"
echo "2. Verify read-only: kubectl --kubeconfig=kgroot-kubeconfig.yaml delete pod test-pod (should fail)"
echo "3. Send kgroot-kubeconfig.yaml to KGroot team securely"
echo ""
echo "To revoke access later:"
echo "  kubectl delete -f k8s-rbac-readonly.yaml"
echo ""
```

### 3. Security Verification Script
```bash
#!/bin/bash
# verify-readonly-access.sh
# Verify that the access is truly read-only

KUBECONFIG_FILE="kgroot-kubeconfig.yaml"

echo "Testing read permissions..."

# Should succeed
kubectl --kubeconfig=$KUBECONFIG_FILE get pods -A > /dev/null 2>&1 && echo "✓ Can read pods" || echo "✗ Cannot read pods"
kubectl --kubeconfig=$KUBECONFIG_FILE get deployments -A > /dev/null 2>&1 && echo "✓ Can read deployments" || echo "✗ Cannot read deployments"
kubectl --kubeconfig=$KUBECONFIG_FILE get events -A > /dev/null 2>&1 && echo "✓ Can read events" || echo "✗ Cannot read events"

echo ""
echo "Testing write permissions (should all fail)..."

# Should fail
kubectl --kubeconfig=$KUBECONFIG_FILE create namespace test-ns > /dev/null 2>&1 && echo "✗ SECURITY ISSUE: Can create namespace" || echo "✓ Cannot create namespace"
kubectl --kubeconfig=$KUBECONFIG_FILE delete pod test-pod -n default > /dev/null 2>&1 && echo "✗ SECURITY ISSUE: Can delete pods" || echo "✓ Cannot delete pods"
kubectl --kubeconfig=$KUBECONFIG_FILE get secrets -A > /dev/null 2>&1 && echo "✗ SECURITY ISSUE: Can read secrets" || echo "✓ Cannot read secrets"
kubectl --kubeconfig=$KUBECONFIG_FILE exec -it test-pod -- ls > /dev/null 2>&1 && echo "✗ SECURITY ISSUE: Can exec into pods" || echo "✓ Cannot exec into pods"

echo ""
echo "Verification complete!"
```

## Alternative Setup Methods

### Method 1: Namespace-Scoped Access (More Restrictive)
If client only wants to grant access to specific namespaces:

```yaml
# namespace-scoped-rbac.yaml
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: kgroot-readonly-role
  namespace: production  # Only for this namespace
rules:
  - apiGroups: ["", "apps", "metrics.k8s.io"]
    resources: ["pods", "pods/log", "deployments", "services", "events"]
    verbs: ["get", "list", "watch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: kgroot-readonly-binding
  namespace: production
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: kgroot-readonly-role
subjects:
  - kind: ServiceAccount
    name: kgroot-readonly-sa
    namespace: kgroot-monitoring
```

### Method 2: Time-Limited Access
For clients who want temporary access:

```yaml
# Include expiration in secret annotation
apiVersion: v1
kind: Secret
metadata:
  name: kgroot-readonly-token
  namespace: kgroot-monitoring
  annotations:
    kubernetes.io/service-account.name: kgroot-readonly-sa
    kgroot.io/expires-at: "2024-12-31T23:59:59Z"
type: kubernetes.io/service-account-token
```

Add cronjob to check and revoke expired tokens:
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: revoke-expired-tokens
  namespace: kgroot-monitoring
spec:
  schedule: "0 0 * * *"  # Daily at midnight
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: token-manager
          containers:
          - name: revoke
            image: bitnami/kubectl:latest
            command:
            - /bin/sh
            - -c
            - |
              CURRENT_DATE=$(date -u +%s)
              for SECRET in $(kubectl get secrets -n kgroot-monitoring -o json | jq -r '.items[] | select(.metadata.annotations["kgroot.io/expires-at"]) | .metadata.name'); do
                EXPIRY=$(kubectl get secret $SECRET -n kgroot-monitoring -o jsonpath='{.metadata.annotations.kgroot\.io/expires-at}')
                EXPIRY_EPOCH=$(date -d $EXPIRY +%s)
                if [ $CURRENT_DATE -gt $EXPIRY_EPOCH ]; then
                  echo "Revoking expired token: $SECRET"
                  kubectl delete secret $SECRET -n kgroot-monitoring
                fi
              done
          restartPolicy: OnFailure
```

## Client Configuration in Your System

After receiving kubeconfig, configure in your system:

```python
# config/client_clusters.py
CLIENTS = {
    'client-alpha': {
        'kubeconfig_path': '/secure/configs/client-alpha-kubeconfig.yaml',
        'cluster_name': 'alpha-prod-cluster',
        'namespaces': ['production', 'staging'],  # Monitor these
        'alert_endpoint': 'https://client-alpha.com/webhook',
        'contact': 'ops@client-alpha.com'
    },
    'client-beta': {
        'kubeconfig_path': '/secure/configs/client-beta-kubeconfig.yaml',
        'cluster_name': 'beta-prod-cluster',
        'namespaces': ['default', 'api'],
        'alert_endpoint': 'https://client-beta.com/webhook',
        'contact': 'devops@client-beta.com'
    }
}
```

```python
# services/multi_cluster_monitor.py
from kubernetes import client, config

class MultiClusterMonitor:
    def __init__(self):
        self.clients = {}
        self._load_clients()

    def _load_clients(self):
        for client_id, client_config in CLIENTS.items():
            try:
                k8s_config = config.load_kube_config(
                    config_file=client_config['kubeconfig_path']
                )
                self.clients[client_id] = {
                    'core_api': client.CoreV1Api(),
                    'apps_api': client.AppsV1Api(),
                    'config': client_config
                }
                print(f"✓ Loaded config for {client_id}")
            except Exception as e:
                print(f"✗ Failed to load config for {client_id}: {e}")

    async def monitor_all_clusters(self):
        tasks = []
        for client_id, k8s_client in self.clients.items():
            task = self.monitor_cluster(client_id, k8s_client)
            tasks.append(task)
        await asyncio.gather(*tasks)

    async def monitor_cluster(self, client_id, k8s_client):
        # Monitor pods, events, etc.
        pass
```

## Security Checklist for Client

Provide this checklist to clients:

- [ ] Service account has NO write permissions
- [ ] Service account has NO secret access
- [ ] Service account has NO exec permissions
- [ ] Token is stored securely (not in version control)
- [ ] Token has expiration date (optional but recommended)
- [ ] K8s audit logging is enabled to track access
- [ ] You can revoke access instantly with: `kubectl delete -f k8s-rbac-readonly.yaml`
- [ ] You've tested that write operations fail
- [ ] You've tested that secret access fails
- [ ] Network policies allow our IPs (if applicable)

## Troubleshooting

### Issue: Token extraction fails
```bash
# Check if secret exists
kubectl get secrets -n kgroot-monitoring

# If using K8s 1.24+, token might not be auto-created
# Manually create token:
kubectl create token kgroot-readonly-sa -n kgroot-monitoring --duration=87600h  # 10 years
```

### Issue: Permission denied errors
```bash
# Check what permissions the SA actually has
kubectl auth can-i --list --as=system:serviceaccount:kgroot-monitoring:kgroot-readonly-sa

# Test specific permission
kubectl auth can-i get pods --as=system:serviceaccount:kgroot-monitoring:kgroot-readonly-sa -A
```

### Issue: Cannot connect to cluster
```bash
# Test connectivity
kubectl --kubeconfig=kgroot-kubeconfig.yaml cluster-info

# Check if firewall allows connection
curl -k https://<cluster-url>:6443
```