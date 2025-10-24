# KGroot RCA - Client Setup Guide

## Overview

This guide helps you (the client) provide **read-only access** to your Kubernetes cluster so that KGroot RCA can monitor events and perform root cause analysis remotely.

**What KGroot RCA will be able to do:**
- ✅ Read events, pods, nodes, deployments, services
- ✅ Watch for failures and performance issues
- ✅ Perform root cause analysis
- ✅ Generate recommendations

**What KGroot RCA will NOT be able to do:**
- ❌ Create, modify, or delete any resources
- ❌ Access secrets or sensitive data
- ❌ Execute commands in pods
- ❌ Make any changes to your cluster

---

## Prerequisites

- `kubectl` installed and configured
- Cluster admin access (to create RBAC)
- Ability to share files securely

---

## Step 1: Apply Read-Only RBAC

This creates a ServiceAccount with minimal read-only permissions:

```bash
# Download the RBAC manifest
curl -O https://your-repo/rbac-readonly.yaml

# Review the manifest (always review before applying!)
cat rbac-readonly.yaml

# Apply to your cluster
kubectl apply -f rbac-readonly.yaml
```

**What this creates:**
- Namespace: `kgroot-monitoring`
- ServiceAccount: `kgroot-readonly`
- ClusterRole: Read-only access to events, pods, nodes, etc.
- ClusterRoleBinding: Binds the role to the ServiceAccount

---

## Step 2: Generate Kubeconfig

This generates a kubeconfig file with the read-only token:

```bash
# Download the script
curl -O https://your-repo/generate-kubeconfig.sh
chmod +x generate-kubeconfig.sh

# Run the script
./generate-kubeconfig.sh
```

**Output:** `kgroot-readonly-kubeconfig.yaml`

The script will:
1. ✅ Verify RBAC is applied
2. ✅ Extract cluster information
3. ✅ Get the ServiceAccount token
4. ✅ Generate a complete kubeconfig file
5. ✅ Verify read-only access works

---

## Step 3: Share Kubeconfig Securely

Send `kgroot-readonly-kubeconfig.yaml` to the RCA team using one of these methods:

### Option A: Encrypted Email
```bash
# Encrypt with GPG (if you have their public key)
gpg --encrypt --recipient rca-team@example.com kgroot-readonly-kubeconfig.yaml

# Send the .gpg file via email
```

### Option B: Secure File Transfer
```bash
# Use your company's secure file sharing (Google Drive, Dropbox, etc.)
# Make sure to set expiration and password protection
```

### Option C: Secrets Manager
```bash
# Upload to your secrets manager (AWS Secrets Manager, Vault, etc.)
# Share access with the RCA team
```

**⚠️ Important:**
- Do NOT send kubeconfig in plain text via Slack/Teams
- Do NOT commit kubeconfig to git
- Use secure channels only

---

## Step 4: Configure Alertmanager (Optional)

If you want KGroot RCA to receive alerts directly from Prometheus Alertmanager:

### Add Webhook Receiver

Edit your `alertmanager.yml`:

```yaml
route:
  receiver: 'default'
  routes:
    # Add this route for KGroot RCA
    - match:
        severity: critical|warning
      receiver: 'kgroot-webhook'
      continue: true  # Keep sending to other receivers too

receivers:
  - name: 'default'
    # Your existing receivers

  - name: 'kgroot-webhook'
    webhook_configs:
      - url: 'http://<RCA_TEAM_IP>:8080/webhook'
        send_resolved: true
```

Replace `<RCA_TEAM_IP>` with the IP address provided by the RCA team.

### Apply Configuration

```bash
# Reload Alertmanager
kubectl -n monitoring rollout restart deployment alertmanager
# Or if using Prometheus Operator:
kubectl -n monitoring delete pod -l app=alertmanager
```

---

## Step 5: Verify Access

The RCA team should now be able to:

```bash
# On their side, they will test:
export KUBECONFIG=/path/to/kgroot-readonly-kubeconfig.yaml

# Test read access
kubectl get nodes
kubectl get events --all-namespaces
kubectl get pods --all-namespaces

# These should fail (no write access):
kubectl create namespace test  # ❌ Should fail
kubectl delete pod xyz          # ❌ Should fail
```

---

## Security Best Practices

### 1. Regular Token Rotation

Rotate the token every 90 days:

```bash
# Delete old token
kubectl delete secret kgroot-readonly-token -n kgroot-monitoring

# Re-apply RBAC (creates new token)
kubectl apply -f rbac-readonly.yaml

# Generate new kubeconfig
./generate-kubeconfig.sh

# Send new kubeconfig to RCA team
```

### 2. Monitor Access

Check what the ServiceAccount is accessing:

```bash
# View recent API calls (requires audit logging enabled)
kubectl get events -n kgroot-monitoring

# Check ClusterRoleBinding
kubectl describe clusterrolebinding kgroot-readonly-binding
```

### 3. Namespace Restrictions (Optional)

If you want to limit access to specific namespaces only:

```yaml
# Instead of ClusterRoleBinding, use RoleBinding per namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: kgroot-readonly-binding
  namespace: production  # Only this namespace
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kgroot-readonly-role
subjects:
  - kind: ServiceAccount
    name: kgroot-readonly
    namespace: kgroot-monitoring
```

---

## Revoke Access

To completely remove access:

```bash
# Delete the ClusterRoleBinding (stops all access immediately)
kubectl delete clusterrolebinding kgroot-readonly-binding

# Delete the namespace (removes ServiceAccount and Secret)
kubectl delete namespace kgroot-monitoring

# Notify the RCA team that access has been revoked
```

---

## Troubleshooting

### Token Not Generated

If `generate-kubeconfig.sh` fails to get the token:

```bash
# Check if secret exists
kubectl get secret -n kgroot-monitoring

# If missing, delete and re-create:
kubectl delete secret kgroot-readonly-token -n kgroot-monitoring
kubectl apply -f rbac-readonly.yaml

# Wait 10 seconds and try again
./generate-kubeconfig.sh
```

### Access Denied Errors

If the RCA team reports access denied errors:

```bash
# Verify RBAC is applied correctly
kubectl get clusterrole kgroot-readonly-role
kubectl get clusterrolebinding kgroot-readonly-binding

# Check ServiceAccount
kubectl get serviceaccount kgroot-readonly -n kgroot-monitoring

# Test access locally
kubectl --as=system:serviceaccount:kgroot-monitoring:kgroot-readonly get nodes
```

### Expired Token

Kubernetes tokens may expire. If access stops working:

```bash
# Regenerate token
kubectl delete secret kgroot-readonly-token -n kgroot-monitoring
kubectl apply -f rbac-readonly.yaml
./generate-kubeconfig.sh

# Send new kubeconfig to RCA team
```

---

## FAQ

### Q: Can KGroot RCA modify my cluster?
**A:** No. The RBAC only grants read permissions. All write/delete operations will be denied.

### Q: Can KGroot RCA read my secrets?
**A:** No. The RBAC does not include read access to Secret values.

### Q: What if I have multiple clusters?
**A:** Repeat the process for each cluster. Each will have its own kubeconfig file.

### Q: How do I know what KGroot is doing?
**A:** Enable Kubernetes audit logging to see all API calls made by the ServiceAccount.

### Q: Can I limit access to specific namespaces?
**A:** Yes. Replace ClusterRoleBinding with per-namespace RoleBindings (see Security Best Practices above).

### Q: What happens if the token is compromised?
**A:** Immediately delete the ClusterRoleBinding to revoke access, then regenerate with a new token.

---

## Support

If you encounter issues:
1. Check the Troubleshooting section above
2. Review Kubernetes RBAC documentation
3. Contact the RCA team for assistance

---

## Appendix: Manual Kubeconfig Creation

If the script doesn't work, you can create the kubeconfig manually:

```bash
# Get cluster info
CLUSTER_NAME=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}')
CLUSTER_SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CLUSTER_CA=$(kubectl get secret kgroot-readonly-token -n kgroot-monitoring -o jsonpath='{.data.ca\.crt}')
TOKEN=$(kubectl get secret kgroot-readonly-token -n kgroot-monitoring -o jsonpath='{.data.token}' | base64 -d)

# Create kubeconfig
cat > kgroot-readonly-kubeconfig.yaml <<EOF
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
current-context: kgroot-readonly@$CLUSTER_NAME
users:
- name: kgroot-readonly
  user:
    token: $TOKEN
EOF
```

---

**End of Client Setup Guide**
