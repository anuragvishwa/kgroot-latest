# Quick Start Guide - v2.0.0

**Zero-touch multi-tenant observability with automatic graph-builder spawning**

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- Helm 3.x installed
- Mini-server running with control plane deployed

## Installation

### Step 1: Add Helm Repositories

```bash
helm repo add anuragvishwa https://anuragvishwa.github.io/kgroot-latest/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

### Step 2: Install Prometheus Stack

```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.enabled=false
```

**Wait for Prometheus to be ready:**
```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=prometheus \
  -n observability \
  --timeout=180s
```

### Step 3: Install KG RCA Agent v2.0.0

**⚠️ Change `client.id` for each cluster to ensure proper multi-tenant isolation!**

```bash
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.0 \
  --namespace observability \
  --set client.id="af-4" \
  --set cluster.name="production-us-east" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090" \
  --set alertsWebhook.enabled=false \
  --set vector.rawLogsTopic=raw.k8s.logs \
  --set eventExporter.rawTopic=raw.k8s.events
```

**What happens automatically:**
1. ✅ Post-install hook registers cluster to `cluster.registry` topic
2. ✅ Control plane sees registration and spawns `kg-graph-builder-af-4`
3. ✅ State-watcher starts sending heartbeats every 30s
4. ✅ Graph-builder begins consuming and storing data in Neo4j

**Wait for pods to be ready:**
```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/instance=kg-rca-agent \
  -n observability \
  --timeout=180s
```

### Step 4: Configure Alertmanager (Optional)

```bash
kubectl create secret generic alertmanager-kube-prometheus-stack-alertmanager \
  --from-literal=alertmanager.yaml="$(cat <<'EOF'
global:
  resolve_timeout: 5m
receivers:
- name: "null"
- name: "kg-alert-receiver"
  webhook_configs:
  - url: "http://kg-rca-agent-kg-rca-agent-alert-receiver.observability.svc:9093/webhook"
    send_resolved: true
route:
  group_by: [namespace]
  group_interval: 5m
  group_wait: 30s
  receiver: "kg-alert-receiver"
  repeat_interval: 12h
  routes:
  - matchers:
    - alertname = "Watchdog"
    receiver: "null"
EOF
)" \
  --namespace observability \
  --dry-run=client -o yaml | kubectl apply -f -
```

**Restart Alertmanager:**
```bash
kubectl delete pod alertmanager-kube-prometheus-stack-alertmanager-0 -n observability
```

### Step 5: Install Bug Scenarios for Testing (Optional)

```bash
helm install bugs anuragvishwa/bugs \
  --namespace buglab \
  --create-namespace
```

## Verification

### Check Kubernetes Pods

```bash
echo "=== Observability Stack ==="
kubectl get pods -n observability

echo ""
echo "=== Bug Scenarios ==="
kubectl get pods -n buglab
```

**Expected output:**
```
=== Observability Stack ===
NAME                                                        READY   STATUS    RESTARTS   AGE
alertmanager-kube-prometheus-stack-alertmanager-0           2/2     Running   0          5m
kg-rca-agent-event-exporter-xxxxx                           1/1     Running   0          2m
kg-rca-agent-state-watcher-xxxxx                            1/1     Running   0          2m
kg-rca-agent-vector-xxxxx                                   1/1     Running   0          2m
kube-prometheus-stack-operator-xxxxx                        1/1     Running   0          5m
kube-prometheus-stack-prometheus-node-exporter-xxxxx        1/1     Running   0          5m
prometheus-kube-prometheus-stack-prometheus-0               2/2     Running   0          5m
```

### Check Mini-Server (Control Plane)

On the mini-server:

```bash
# Check if graph-builder was auto-spawned
ssh mini-server 'docker ps | grep graph-builder'

# Expected output:
# kg-graph-builder-af-4   anuragvishwa/kg-graph-builder:1.0.20   Up 2 minutes

# Check control plane logs
ssh mini-server 'docker logs kg-control-plane | tail -20'

# Expected logs:
# 📝 Cluster registered: af-4 (name: production-us-east, version: 2.0.0)
# 🔧 Spawning graph-builder for cluster: af-4
# ✅ Spawned graph-builder-af-4 (container: abc123...)
# 💓 Heartbeat received from: af-4

# Check Prometheus metrics
ssh mini-server 'curl -s http://localhost:9090/metrics | grep kg_control_plane_clusters_total'

# Expected output:
# kg_control_plane_clusters_total{status="active"} 1
```

### Verify Kafka Topics

```bash
# Check cluster.registry
ssh mini-server 'docker exec kg-kafka kafka-topics --bootstrap-server kg-kafka:29092 --list | grep cluster'

# Expected output:
# cluster.heartbeat
# cluster.registry

# View registration
ssh mini-server 'docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --property print.key=true \
  --from-beginning \
  --max-messages 1'

# Expected output:
# af-4:{"client_id":"af-4","cluster_name":"production-us-east","version":"2.0.0",...}
```

## Testing Auto-Cleanup

When you delete the Helm release, everything is automatically cleaned up:

```bash
# Delete the release
helm delete kg-rca-agent -n observability

# Pre-delete hook sends tombstone to cluster.registry
# Control plane sees tombstone and:
# 1. Stops kg-graph-builder-af-4 container
# 2. Deletes consumer group kg-builder-af-4
# 3. Removes cluster from active list

# Verify cleanup on mini-server
ssh mini-server 'docker ps | grep graph-builder-af-4'
# (should be empty)

ssh mini-server 'docker logs kg-control-plane | tail -10'
# Expected logs:
# 🪦 Cluster deregistered: af-4
# 💀 Cleaning up dead cluster: af-4
# 🛑 Stopping container: abc123...
# 🗑️  Deleting consumer group: kg-builder-af-4
# ✅ Cleaned up cluster: af-4
```

## Multi-Cluster Deployment

Deploy to multiple clusters with different `client.id` values:

```bash
# Cluster 1 (af-4)
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.0 \
  --namespace observability \
  --set client.id="af-4" \
  --set cluster.name="prod-us-east" \
  --set client.kafka.brokers="98.90.147.12:9092"

# Cluster 2 (af-5)
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.0 \
  --namespace observability \
  --set client.id="af-5" \
  --set cluster.name="prod-eu-west" \
  --set client.kafka.brokers="98.90.147.12:9092"

# Cluster 3 (af-6)
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.0 \
  --namespace observability \
  --set client.id="af-6" \
  --set cluster.name="staging-us-west" \
  --set client.kafka.brokers="98.90.147.12:9092"
```

**Result on mini-server:**
```bash
docker ps | grep graph-builder
# kg-graph-builder-af-4   Up 10 minutes
# kg-graph-builder-af-5   Up 8 minutes
# kg-graph-builder-af-6   Up 5 minutes

curl -s http://localhost:9090/metrics | grep clusters_total
# kg_control_plane_clusters_total{status="active"} 3
```

## Troubleshooting

### Graph-builder not spawned

**Check control plane logs:**
```bash
ssh mini-server 'docker logs kg-control-plane | grep af-4'
```

**Common issues:**
- Registration message not sent (check post-install job logs)
- Control plane not watching registry (restart control plane)
- Docker socket permission issue (check volume mount)

### Heartbeats not received

**Check state-watcher logs:**
```bash
kubectl logs -n observability deployment/kg-rca-agent-state-watcher | grep heartbeat
```

**Common issues:**
- CLIENT_ID env var not set (check deployment)
- Kafka connectivity issue (check network)
- Topic doesn't exist (recreate topics)

### Data not in Neo4j

**Check graph-builder logs:**
```bash
ssh mini-server 'docker logs kg-graph-builder-af-4 | tail -50'
```

**Common issues:**
- Consumer lag (check offset)
- Neo4j connection failed (check credentials)
- CLIENT_ID mismatch (check env var)

## Monitoring

### Prometheus Metrics

Control plane exposes metrics on `:9090/metrics`:

```bash
curl http://98.90.147.12:9090/metrics | grep kg_control_plane

# Key metrics:
# kg_control_plane_clusters_total{status="active"} - Active clusters
# kg_control_plane_clusters_total{status="stale"} - Stale clusters (>2min no heartbeat)
# kg_control_plane_clusters_total{status="dead"} - Dead clusters (>5min no heartbeat)
# kg_control_plane_spawn_operations_total - Total spawns
# kg_control_plane_cleanup_operations_total - Total cleanups
```

### Kafka Topic Monitoring

```bash
# Registry
ssh mini-server 'docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.registry \
  --property print.key=true \
  --from-beginning'

# Heartbeats (live)
ssh mini-server 'docker exec kg-kafka kafka-console-consumer \
  --bootstrap-server kg-kafka:29092 \
  --topic cluster.heartbeat \
  --property print.key=true'
```

## What's New in v2.0.0

### Control Plane Architecture
- ✅ **Auto-discovery**: Clusters auto-register via `cluster.registry` topic
- ✅ **Dynamic spawning**: Graph-builders spawned automatically per cluster
- ✅ **Heartbeat monitoring**: 30-second heartbeats detect cluster health
- ✅ **Auto-cleanup**: Dead clusters (>5min) automatically cleaned up
- ✅ **Self-healing**: Crashed graph-builders auto-restart

### Client-Side Changes
- ✅ **Registration hooks**: Post-install/pre-delete Helm hooks
- ✅ **Heartbeat sender**: State-watcher sends heartbeats
- ✅ **Cluster metadata**: Optional `cluster.name` field

### Operational Benefits
- 🚀 **Zero-touch**: `helm install` → auto-spawn, `helm delete` → auto-cleanup
- 📊 **Observability**: Prometheus metrics for cluster health
- 🔄 **Self-healing**: Automatic recovery from failures
- 🎯 **Multi-tenant**: 100+ clusters supported with minimal overhead

## Related Documentation

- [CONTROL-PLANE-ARCHITECTURE.md](CONTROL-PLANE-ARCHITECTURE.md) - Architecture design
- [CONTROL-PLANE-IMPLEMENTATION.md](CONTROL-PLANE-IMPLEMENTATION.md) - Implementation guide
- [MULTI-TENANT-ARCHITECTURE.md](MULTI-TENANT-ARCHITECTURE.md) - Multi-tenant overview
- [control-plane/README.md](control-plane/README.md) - Control plane documentation

## Support

- 📖 Documentation: https://github.com/anuragvishwa/kgroot-latest
- 🐛 Issues: https://github.com/anuragvishwa/kgroot-latest/issues
- 💬 Discussions: https://github.com/anuragvishwa/kgroot-latest/discussions

## License

Apache 2.0
