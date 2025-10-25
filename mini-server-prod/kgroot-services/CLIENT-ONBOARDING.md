# KGroot RCA - Client Onboarding Instructions

Dear Client,

Thank you for choosing our KGroot RCA (Root Cause Analysis) service. This guide will help you provide us with **read-only access** to monitor your Kubernetes cluster for proactive incident detection and analysis.

---

## 🔐 Security First

**What we need:**
- ✅ Read-only access to K8s events, pods, nodes, deployments
- ✅ Webhook endpoint for Prometheus Alertmanager

**What we DON'T need:**
- ❌ Write/delete permissions
- ❌ Access to Secret values
- ❌ SSH access to nodes
- ❌ Database credentials

---

## 📋 Setup Steps (15 minutes)

### Option A: Alertmanager Webhook Only (Recommended - 5 min)

**Easiest setup, no kubeconfig needed**

1. Edit your Alertmanager configuration (`alertmanager.yml`):

```yaml
route:
  receiver: 'default'
  routes:
    # Add this route for KGroot RCA
    - match:
        severity: critical|warning
      receiver: 'kgroot-rca'
      continue: true  # Keep sending to your existing receivers

receivers:
  - name: 'default'
    # Your existing receivers...

  - name: 'kgroot-rca'
    webhook_configs:
      - url: 'http://YOUR_RCA_SERVER_IP:8081/webhook'
        send_resolved: true
```

2. Replace `YOUR_RCA_SERVER_IP` with: **`<WE_WILL_PROVIDE_THIS>`**

3. Reload Alertmanager:
```bash
kubectl -n monitoring rollout restart deployment alertmanager
# Or if using Prometheus Operator:
kubectl -n monitoring delete pod -l app=alertmanager
```

4. Test the webhook:
```bash
curl -X POST http://YOUR_RCA_SERVER_IP:8081/health
# Should return: {"status":"healthy","rca_enabled":true}
```

**✅ Done! You're all set.**

---

### Option B: Full Access with K8s Event Monitoring (Optional - 15 min)

**Provides better accuracy with real-time K8s event monitoring**

#### Step 1: Apply Read-Only RBAC

```bash
# Download the RBAC manifest
wget https://YOUR_REPO/rbac-readonly.yaml
# Or use the attached rbac-readonly.yaml file

# Review it (ALWAYS review before applying!)
cat rbac-readonly.yaml

# Apply to your cluster
kubectl apply -f rbac-readonly.yaml
```

**What this creates:**
- Namespace: `kgroot-monitoring`
- ServiceAccount: `kgroot-readonly`
- ClusterRole: Read-only access
- ClusterRoleBinding: Binds the role

#### Step 2: Generate Kubeconfig

```bash
# Download the script
wget https://YOUR_REPO/generate-kubeconfig.sh
chmod +x generate-kubeconfig.sh

# Run it
./generate-kubeconfig.sh
```

**Output:** `kgroot-readonly-kubeconfig.yaml`

#### Step 3: Share Kubeconfig Securely

**Option 1: Encrypted Email**
```bash
# Encrypt with our public key
gpg --encrypt --recipient rca-team@yourcompany.com kgroot-readonly-kubeconfig.yaml
# Email the .gpg file
```

**Option 2: Secure File Share**
- Upload to your secure file sharing (Google Drive, Dropbox, AWS S3)
- Set password protection and expiration
- Share the link with us

**Option 3: Direct Transfer**
```bash
# If you have scp access to our server
scp kgroot-readonly-kubeconfig.yaml rca-user@YOUR_RCA_SERVER:/path/to/configs/
```

**⚠️ IMPORTANT:**
- Do NOT send kubeconfig via plain Slack/Teams/Email
- Do NOT commit to git
- Use encrypted channels only

---

## 🧪 Testing

### Test 1: Verify Webhook Works

```bash
curl -X POST http://YOUR_RCA_SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "service": "test-service",
        "namespace": "default"
      },
      "annotations": {
        "summary": "Test alert from your cluster"
      }
    }]
  }'
```

**Expected Response:** `{"status":"ok","processed":1}`

### Test 2: Trigger RCA Analysis

Send 3 alerts quickly to trigger analysis:

```bash
# Alert 1
curl -X POST http://YOUR_RCA_SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"labels":{"alertname":"HighMemory","severity":"warning","service":"test-app"},"annotations":{"summary":"Memory at 85%"}}]}'

# Alert 2
curl -X POST http://YOUR_RCA_SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"labels":{"alertname":"PodRestart","severity":"critical","service":"test-app"},"annotations":{"summary":"Pod crashed"}}]}'

# Alert 3
curl -X POST http://YOUR_RCA_SERVER_IP:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"labels":{"alertname":"HighErrors","severity":"critical","service":"test-app"},"annotations":{"summary":"Error rate high"}}]}'
```

**Expected:** RCA analysis will run and provide:
- Root cause identification
- Top 3 solutions with success probabilities
- Blast radius analysis
- Impact assessment
- Actionable kubectl commands

Check our dashboard or we'll share the results with you!

---

## 📊 What You'll Get

Once integrated, for every incident you'll receive:

### 1. Immediate Root Cause Analysis
```
🎯 Root Cause: memory_high in payment-service (99% confidence)
💡 Summary: Memory leak causing OOM restarts and cascading failures
```

### 2. Blast Radius Assessment
```
💥 Blast Radius:
   - Impact: payment-service degraded, 40% transactions failing
   - User Impact: 25% of active users affected
   - Downstream: order-service, inventory-service
```

### 3. Prioritized Actions
```
🚨 Priority: P0-Critical
   Time to Action: Immediate - within 5 minutes
   Team: platform-team
```

### 4. Top 3 Solutions
```
📋 Solution 1: Increase memory limits (95% success rate)
   ├─ Blast Radius: Low
   ├─ Risk Level: Low
   ├─ Downtime: 30 seconds
   └─ Steps: kubectl set resources...

📋 Solution 2: Scale horizontally (85% success rate)
   ├─ Blast Radius: Medium
   ├─ Risk Level: Medium
   └─ Steps: kubectl scale...

📋 Solution 3: Deploy memory fix (70% success rate)
   ├─ Blast Radius: High
   └─ Long-term solution
```

---

## 🔧 Maintenance

### Token Rotation (Every 90 Days)

```bash
# Delete old token
kubectl delete secret kgroot-readonly-token -n kgroot-monitoring

# Re-apply RBAC (creates new token)
kubectl apply -f rbac-readonly.yaml

# Generate new kubeconfig
./generate-kubeconfig.sh

# Send us the new kubeconfig
```

### Revoke Access

```bash
# Immediately revoke all access
kubectl delete clusterrolebinding kgroot-readonly-binding

# Complete cleanup
kubectl delete namespace kgroot-monitoring

# Notify us that access has been revoked
```

---

## ❓ FAQ

**Q: Can you modify our cluster?**
A: No. The RBAC only grants read permissions. All write/delete operations will be denied.

**Q: Can you read our secrets?**
A: No. The RBAC does not include read access to Secret values.

**Q: What if the token is compromised?**
A: Immediately delete the ClusterRoleBinding to revoke access, then regenerate with a new token.

**Q: Do you store our data?**
A: We only store event patterns (anonymized) for improving RCA accuracy. No sensitive data is stored.

**Q: What's the cost?**
A: Pricing based on cluster size and alert volume. Contact us for details.

---

## 📞 Support

**For setup help:**
- Email: support@yourcompany.com
- Slack: #kgroot-rca-support
- Phone: +1-XXX-XXX-XXXX

**For emergencies:**
- On-call: +1-XXX-XXX-XXXX (24/7)

---

## 📎 Attachments

This package includes:
- ✅ `rbac-readonly.yaml` - K8s RBAC manifest
- ✅ `generate-kubeconfig.sh` - Kubeconfig generator script
- ✅ `CLIENT-SETUP-GUIDE.md` - Detailed technical guide

---

**Thank you for trusting us with your incident response!**

Best regards,
The KGroot RCA Team
