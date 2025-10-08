# Cleanup Commands - Remove Useless Minikube Pods

## Already Cleaned Up ✅

These were already removed during migration:
- ✅ `kafka-0` (StatefulSet)
- ✅ `neo4j-0` (StatefulSet)
- ✅ `kafka-ui` (Deployment)
- ✅ `kg-builder` (Deployment)
- ✅ `kg-init-schema` (Job)

## Current Minikube Pods (All Needed ✅)

```bash
$ kubectl get pods -n observability
NAME                                  READY   STATUS    RESTARTS   AGE
k8s-event-exporter-65667c7775-wlkf8   1/1     Running   0          2m
state-watcher-bb9777948-grzzm         1/1     Running   0          7m
vector-6bc489d745-fzltd               1/1     Running   0          2m
vector-logs-j6xkv                     1/1     Running   0          2m
```

**All of these are needed and actively producing to Docker Kafka! Don't delete them.**

---

## Optional: Remove Orphaned Resources

### 1. Remove Orphaned PVCs (if they exist)

```bash
# Check for orphaned PVCs
kubectl get pvc -n observability

# Remove kafka/neo4j PVCs if they exist
kubectl delete pvc data-kafka-0 data-neo4j-0 -n observability 2>/dev/null || echo "No orphaned PVCs"
```

### 2. Remove Old Services (if they exist)

```bash
# Check for old services
kubectl get svc -n observability

# Remove old kafka/neo4j services
kubectl delete svc kafka kafka-external kafka-ui neo4j -n observability 2>/dev/null || echo "No orphaned services"
```

### 3. Remove Old ConfigMaps (CAREFUL!)

```bash
# Check current configmaps
kubectl get configmap -n observability

# DON'T DELETE THESE (they're in use):
# - kgroot-env (used by state-watcher)
# - k8s-event-exporter-config
# - vector-config
# - vector-logs-config
# - kube-root-ca.crt

# Only delete if you see old kafka/neo4j configmaps:
# kubectl delete configmap <old-configmap-name> -n observability
```

### 4. Check for Failed/Completed Jobs

```bash
# List all jobs
kubectl get jobs -n observability

# Delete completed/failed jobs
kubectl delete job kg-init-schema -n observability 2>/dev/null || echo "No orphaned jobs"

# Clean up all completed jobs automatically
kubectl delete job --field-selector status.successful=1 -n observability
kubectl delete job --field-selector status.failed=1 -n observability
```

---

## Remove Docker Orphaned Containers

```bash
# Check for orphaned containers
docker ps -a | grep -i "exited\|created"

# Remove the kafka-init container (it's a one-time setup)
docker compose down --remove-orphans

# Or manually:
docker rm kgroot_latest-kg-init-1 2>/dev/null || echo "Already removed"
```

---

## Full Cleanup Script (Safe)

```bash
#!/bin/bash
echo "🧹 Cleaning up orphaned resources..."

# Remove orphaned PVCs
echo "Checking for orphaned PVCs..."
kubectl delete pvc data-kafka-0 data-neo4j-0 -n observability 2>/dev/null || echo "✅ No orphaned PVCs"

# Remove old services
echo "Checking for old services..."
kubectl delete svc kafka kafka-external kafka-ui neo4j -n observability 2>/dev/null || echo "✅ No orphaned services"

# Remove completed jobs
echo "Checking for completed jobs..."
kubectl delete job --field-selector status.successful=1 -n observability 2>/dev/null || echo "✅ No completed jobs"
kubectl delete job --field-selector status.failed=1 -n observability 2>/dev/null || echo "✅ No failed jobs"

# Docker cleanup
echo "Removing Docker orphaned containers..."
docker compose down --remove-orphans 2>/dev/null || echo "✅ No orphaned Docker containers"

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "Current status:"
kubectl get pods,svc,pvc -n observability
```

---

## What NOT to Delete

### Minikube Pods (All Needed!)
- ❌ **state-watcher** - Watches K8s resources
- ❌ **k8s-event-exporter** - Exports K8s events
- ❌ **vector** - Collects Prometheus alerts
- ❌ **vector-logs** - Collects pod logs

### Docker Containers (All Needed!)
- ❌ **kafka** - Message broker
- ❌ **zookeeper** - Kafka coordination
- ❌ **neo4j** - Graph database
- ❌ **kafka-ui** - Web UI
- ❌ **graph-builder** - Knowledge graph builder
- ❌ **alerts-enricher** - Alert enrichment

### ConfigMaps (Keep These!)
- ❌ **kgroot-env** - Environment variables
- ❌ **vector-config** - Vector configuration
- ❌ **vector-logs-config** - Vector logs config
- ❌ **k8s-event-exporter-config** - Event exporter config

---

## Verify After Cleanup

```bash
# Check minikube pods are all running
kubectl get pods -n observability

# Check Docker containers are healthy
docker ps

# Verify messages are still flowing
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group kg-builder
```

---

## Summary

**Safe to remove:**
- ✅ Orphaned PVCs (data-kafka-0, data-neo4j-0)
- ✅ Old services (kafka, kafka-external, kafka-ui, neo4j)
- ✅ Completed/failed jobs (kg-init-schema)
- ✅ Docker orphaned containers (kg-init)

**DO NOT remove:**
- ❌ Any running pods (state-watcher, vector, vector-logs, k8s-event-exporter)
- ❌ Active Docker containers
- ❌ ConfigMaps (they're all in use)
- ❌ Prometheus stack (monitoring namespace)

---

**Everything else is either already cleaned up or actively in use!**
