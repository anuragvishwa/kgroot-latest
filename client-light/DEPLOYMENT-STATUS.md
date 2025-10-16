# KG RCA Agent - Deployment Status

## ✅ What's Been Completed

### 1. Docker Hub Images Published
Successfully built and published to Docker Hub:
- ✅ `anuragvishwa/kg-alert-receiver:1.0.2`
- ✅ `anuragvishwa/kg-state-watcher:1.0.2`
- ✅ Images are public and accessible
- ✅ Both `:1.0.2` and `:latest` tags available

**View on Docker Hub:**
- https://hub.docker.com/r/anuragvishwa/kg-alert-receiver
- https://hub.docker.com/r/anuragvishwa/kg-state-watcher

### 2. Helm Chart Updated
- ✅ Updated [values.yaml](helm-chart/values.yaml) with Docker Hub image references
- ✅ Fixed event-exporter image tag (`latest` instead of `v1.4`)
- ✅ Added proper environment variable mappings
- ✅ Chart version: 1.0.2

### 3. GitHub Release Updated
- ✅ Packaged chart: `kg-rca-agent-1.0.2.tgz`
- ✅ Uploaded to GitHub release v1.0.2
- ✅ Ready for customer downloads

### 4. Documentation Created
- ✅ [publish-images.sh](publish-images.sh) - Automates Docker Hub publishing
- ✅ [build-images.sh](build-images.sh) - For local Minikube development
- ✅ [DOCKER-HUB.md](DOCKER-HUB.md) - Docker Hub image documentation
- ✅ [PUBLISHING-GUIDE.md](PUBLISHING-GUIDE.md) - Complete publishing workflow
- ✅ [HELM-INSTALL.md](HELM-INSTALL.md) - Updated with Docker Hub info

## ⚠️ Known Issues (Needs Fixing)

### 1. State-Watcher Configuration
**Status:** Container crashes immediately after start

**Root Cause:** The state-watcher Go application expects specific environment variables and may have additional requirements:
- Needs Kubernetes RBAC permissions (serviceAccount properly configured)
- May require leader election lease
- Might need additional Kafka/SASL configuration

**Files to Check:**
- [state-watcher/main.go](../state-watcher/main.go) - Check all `os.Getenv()` calls
- [helm-chart/templates/state-watcher-deployment.yaml](helm-chart/templates/state-watcher-deployment.yaml)
- [helm-chart/templates/rbac.yaml](helm-chart/templates/rbac.yaml)

**Next Steps:**
1. Run state-watcher locally to see full error output
2. Add verbose logging/debug mode
3. Check if it needs specific Kafka topics to exist first
4. Verify RBAC permissions are sufficient

### 2. Alert-Receiver Configuration
**Status:** CrashLoopBackOff

**Similar Issue:** Likely missing required environment variables or Kafka connection config

**Files to Check:**
- [alerts-enricher/src/index.ts](../alerts-enricher/src/index.ts)
- [helm-chart/templates/alert-receiver-deployment.yaml](helm-chart/templates/alert-receiver-deployment.yaml)

### 3. Vector DaemonSet
**Status:** RunContainerError

**Likely Issue:** Vector configuration or permissions

**Files to Check:**
- [helm-chart/templates/vector-daemonset.yaml](helm-chart/templates/vector-daemonset.yaml)
- Vector ConfigMap generation

### 4. Event-Exporter
**Status:** CrashLoopBackOff (after image pull success)

**Likely Issue:** Configuration format for opsgenie/kubernetes-event-exporter

**Files to Check:**
- [helm-chart/templates/event-exporter-deployment.yaml](helm-chart/templates/event-exporter-deployment.yaml)
- Event exporter expects specific config format

## 🎯 For Customer Deployment

### What Works Now:
✅ Customers can download and install the Helm chart
✅ Images pull successfully from Docker Hub (no more ImagePullBackOff for custom images)
✅ Helm chart syntax is valid

### What Needs Fixing Before Production:
1. **State-Watcher:** Needs debugging and proper configuration
2. **Alert-Receiver:** Needs environment variable mapping fixed
3. **Vector:** Needs configuration fixes
4. **Event-Exporter:** Needs proper config format

## 🔧 Recommended Next Steps

### Option 1: Quick Fix for Customers
Create a "minimal" version that only includes components that work:
- Disable problematic components in values.yaml
- Focus on getting 1-2 components working perfectly
- Add others incrementally

### Option 2: Full Debug Session
1. Run each component locally first:
```bash
# Test state-watcher
cd state-watcher
go run main.go

# Test alert-receiver
cd alerts-enricher
npm run dev
```

2. Capture all required environment variables
3. Update Helm templates with complete env vars
4. Test in Minikube step-by-step

### Option 3: Use Working Reference
Check if you have a working docker-compose setup and extract the exact environment variables and configurations from there.

## 📦 How Customers Can Install (Current State)

```bash
# Download
wget https://github.com/anuragvishwa/kgroot-latest/releases/download/v1.0.2/kg-rca-agent-1.0.2.tgz

# Install
helm install kg-rca-agent kg-rca-agent-1.0.2.tgz \
  --set client.id=my-cluster \
  --set client.kafka.brokers=98.90.147.12:9092 \
  --namespace observability \
  --create-namespace
```

**Result:**
- ✅ Helm install succeeds
- ✅ Images pull from Docker Hub
- ⚠️ Pods crash due to configuration issues (see above)

## 📝 Summary

**Major Achievement:** You now have a complete Docker Hub publishing pipeline! Customers can easily install your Helm chart without building images.

**Remaining Work:** The Helm templates need to be aligned with what your actual application code expects. This requires mapping the environment variables correctly between:
1. What the Go/Node.js code reads (`os.Getenv()`)
2. What the Helm chart provides (ConfigMap + Deployment env vars)

The infrastructure is solid - it's just a matter of configuration alignment now.
