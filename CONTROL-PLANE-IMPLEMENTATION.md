# Control Plane Implementation Guide

**Version 2.0.0 - Zero-Touch Multi-Tenant Operations**

## Overview

This guide walks through implementing the control plane architecture for dynamic graph-builder spawning.

## What's Been Implemented

### 1. Control Plane Manager ([control-plane/](control-plane/))

**Files:**
- `main.go` - Core control plane logic
- `Dockerfile` - Multi-arch Docker build
- `go.mod` / `go.sum` - Dependencies
- `README.md` - Documentation
- `build-and-push.sh` - Build script

**Features:**
- ✅ Watches `cluster.registry` topic for cluster registrations
- ✅ Watches `cluster.heartbeat` topic for liveness
- ✅ Reconciliation loop (every 30s) for spawn/cleanup
- ✅ Dynamic graph-builder container spawning via Docker API
- ✅ Auto-cleanup of dead clusters (>5min no heartbeat)
- ✅ Prometheus metrics on `:9090/metrics`

### 2. Client-Side Changes

#### Helm Chart Updates ([client-light/helm-chart/](client-light/helm-chart/))

**New Files:**
- `templates/register-cluster-job.yaml` - Post-install hook
- `templates/deregister-cluster-job.yaml` - Pre-delete hook

**Modified Files:**
- `Chart.yaml` - Version bumped to 2.0.0
- `values.yaml` - Added `cluster.name` field

**Features:**
- ✅ Post-install hook sends registration to `cluster.registry`
- ✅ Pre-delete hook sends tombstone to `cluster.registry`

#### State-Watcher Updates ([state-watcher/main.go](state-watcher/main.go))

**Changes:**
- Added `runHeartbeat()` function
- Sends heartbeat every 30s to `cluster.heartbeat` topic
- Includes metrics (resources_sent, uptime_seconds)

### 3. Infrastructure Updates

**New File:**
- `mini-server-prod/docker-compose-control-plane.yml` - Full setup with control plane

## Implementation Steps

### Phase 1: Build and Push Images

#### 1.1 Build Control Plane

```bash
cd control-plane
./build-and-push.sh
```

This will:
- Build multi-arch image (amd64 + arm64)
- Push to Docker Hub as `anuragvishwa/kg-control-plane:1.0.0`
- Also tag as `latest`

#### 1.2 Build State-Watcher (with heartbeat)

```bash
cd state-watcher
docker buildx build --platform linux/amd64,linux/arm64 \
  -t anuragvishwa/kg-state-watcher:1.0.3 \
  -t anuragvishwa/kg-state-watcher:latest \
  --push .
```

Update Helm chart to use new version:
```yaml
# client-light/helm-chart/values.yaml
stateWatcher:
  image:
    tag: "1.0.3"  # Updated from 1.0.2
```

#### 1.3 Update Graph-Builder Image Reference

Ensure control plane uses correct graph-builder image:
```yaml
# In docker-compose-control-plane.yml
environment:
  GRAPH_BUILDER_IMAGE: "anuragvishwa/kg-graph-builder:1.0.20"
```

### Phase 2: Deploy Mini-Server with Control Plane

#### 2.1 Stop Existing Setup (if running)

```bash
ssh mini-server 'cd ~/kgroot-latest/mini-server-prod && docker-compose down'
```

#### 2.2 Create Kafka Topics

```bash
ssh mini-server 'docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic cluster.registry --partitions 3 --replication-factor 1 \
  --config cleanup.policy=compact'

ssh mini-server 'docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic cluster.heartbeat --partitions 3 --replication-factor 1 \
  --config retention.ms=3600000'
```

#### 2.3 Deploy with Control Plane

```bash
# Copy new docker-compose file
scp mini-server-prod/docker-compose-control-plane.yml mini-server:~/kgroot-latest/mini-server-prod/

# Start services
ssh mini-server 'cd ~/kgroot-latest/mini-server-prod && \
  docker-compose -f docker-compose-control-plane.yml up -d'
```

#### 2.4 Verify Control Plane

```bash
# Check logs
ssh mini-server 'docker logs -f kg-control-plane'

# Should see:
# 🚀 Starting Control Plane Manager
# 👀 Watching cluster.registry topic
# 💓 Watching cluster.heartbeat topic
# 📊 Metrics server listening on :9090
```

### Phase 3: Publish Helm Chart v2.0.0

#### 3.1 Package Chart

```bash
cd client-light
helm package helm-chart
# Creates: kg-rca-agent-2.0.0.tgz
```

#### 3.2 Update Helm Repository

```bash
mv kg-rca-agent-2.0.0.tgz ../gh-pages-content/
cd ../gh-pages-content
helm repo index . --url https://anuragvishwa.github.io/kgroot-latest/
git add .
git commit -m "Release Helm chart v2.0.0 with control plane support"
git push origin gh-pages
```

#### 3.3 Verify Helm Chart

```bash
helm repo update
helm search repo anuragvishwa/kg-rca-agent --versions

# Should show:
# NAME                        CHART VERSION   APP VERSION
# anuragvishwa/kg-rca-agent   2.0.0           2.0.0
```

### Phase 4: Test with First Cluster

#### 4.1 Deploy Cluster af-10

```bash
helm upgrade --install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.0 \
  --namespace observability \
  --create-namespace \
  --set client.id="af-10" \
  --set cluster.name="production-us-east" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090"
```

#### 4.2 Watch Control Plane Logs

```bash
ssh mini-server 'docker logs -f kg-control-plane'
```

**Expected Output:**
```
📝 Cluster registered: af-10 (name: production-us-east, version: 2.0.0)
🔧 Spawning graph-builder for cluster: af-10
✅ Spawned graph-builder-af-10 (container: abc123def456)
💓 Heartbeat received from: af-10
```

#### 4.3 Verify Graph-Builder

```bash
ssh mini-server 'docker ps | grep graph-builder'

# Should show:
# kg-graph-builder-af-10   anuragvishwa/kg-graph-builder:1.0.20
```

#### 4.4 Check Kafka Topics

**Registry:**
```bash
ssh mini-server 'docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic cluster.registry \
  --property print.key=true \
  --from-beginning'

# Output:
# af-10:{"client_id":"af-10","cluster_name":"production-us-east","version":"2.0.0",...}
```

**Heartbeats:**
```bash
ssh mini-server 'docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic cluster.heartbeat \
  --property print.key=true'

# Output (every 30s):
# af-10:{"client_id":"af-10","timestamp":"2025-10-23T10:05:00Z","status":"healthy",...}
```

### Phase 5: Test Auto-Cleanup

#### 5.1 Delete Cluster

```bash
helm delete kg-rca-agent -n observability
```

#### 5.2 Watch Control Plane Logs

```bash
ssh mini-server 'docker logs -f kg-control-plane'
```

**Expected Output:**
```
🪦 Cluster deregistered: af-10
💀 Cleaning up dead cluster: af-10
🛑 Stopping container: abc123def456
🗑️  Deleting consumer group: kg-builder-af-10
✅ Cleaned up cluster: af-10
```

#### 5.3 Verify Cleanup

```bash
# Container removed
ssh mini-server 'docker ps -a | grep graph-builder-af-10'
# (should be empty)

# Consumer group deleted
ssh mini-server 'docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list | grep af-10'
# (should be empty)
```

### Phase 6: Test Multi-Tenant

#### 6.1 Deploy Multiple Clusters

```bash
# Cluster af-10
helm install kg-rca-agent-10 anuragvishwa/kg-rca-agent \
  --version 2.0.0 \
  --namespace observability \
  --set client.id="af-10" \
  --set cluster.name="prod-us-east" \
  --set client.kafka.brokers="98.90.147.12:9092"

# Cluster af-11
helm install kg-rca-agent-11 anuragvishwa/kg-rca-agent \
  --version 2.0.0 \
  --namespace observability \
  --set client.id="af-11" \
  --set cluster.name="prod-eu-west" \
  --set client.kafka.brokers="98.90.147.12:9092"
```

#### 6.2 Verify Multiple Graph-Builders

```bash
ssh mini-server 'docker ps | grep graph-builder'

# Should show:
# kg-graph-builder-af-10   anuragvishwa/kg-graph-builder:1.0.20
# kg-graph-builder-af-11   anuragvishwa/kg-graph-builder:1.0.20
```

#### 6.3 Check Prometheus Metrics

```bash
ssh mini-server 'curl -s http://localhost:9090/metrics | grep kg_control_plane'

# Output:
# kg_control_plane_clusters_total{status="active"} 2
# kg_control_plane_spawn_operations_total 2
```

### Phase 7: Test Self-Healing

#### 7.1 Kill Graph-Builder Container

```bash
ssh mini-server 'docker stop kg-graph-builder-af-10'
```

#### 7.2 Wait for Reconciliation

Control plane reconciles every 30s, so within 30 seconds:

```bash
ssh mini-server 'docker logs -f kg-control-plane'

# Output:
# ⚠️  Graph-builder container stopped, respawning: af-10
# 🔧 Spawning graph-builder for cluster: af-10
# ✅ Spawned graph-builder-af-10 (container: xyz789abc123)
```

#### 7.3 Verify Respawn

```bash
ssh mini-server 'docker ps | grep graph-builder-af-10'
# (should show new container running)
```

## Monitoring and Observability

### Prometheus Metrics

Access at `http://98.90.147.12:9090/metrics`:

```
# Clusters by status
kg_control_plane_clusters_total{status="active"} 2
kg_control_plane_clusters_total{status="stale"} 0
kg_control_plane_clusters_total{status="dead"} 0

# Operations
kg_control_plane_spawn_operations_total 3
kg_control_plane_cleanup_operations_total 1
```

### Grafana Dashboard (Optional)

Create dashboard with panels:
- Active clusters count
- Spawn operations rate
- Cleanup operations rate
- Cluster status distribution (pie chart)

## Troubleshooting

### Control Plane Not Spawning

**Check Docker socket access:**
```bash
ssh mini-server 'docker exec kg-control-plane ls -la /var/run/docker.sock'
```

**Check logs:**
```bash
ssh mini-server 'docker logs kg-control-plane | grep ERROR'
```

### Heartbeats Not Received

**Check state-watcher logs:**
```bash
kubectl logs -n observability deployment/kg-rca-agent-state-watcher | grep heartbeat
```

**Verify Kafka connectivity:**
```bash
kubectl exec -n observability deployment/kg-rca-agent-state-watcher -- \
  nc -zv kafka.example.com 9092
```

### Graph-Builder Not Processing

**Check graph-builder logs:**
```bash
ssh mini-server 'docker logs kg-graph-builder-af-10'
```

**Verify Neo4j connection:**
```bash
ssh mini-server 'docker exec kg-graph-builder-af-10 nc -zv kg-neo4j 7687'
```

## Rollback Plan

If issues occur, rollback to v1.0.47:

```bash
# On mini-server
ssh mini-server 'cd ~/kgroot-latest/mini-server-prod && \
  docker-compose -f docker-compose.yml up -d'

# On Kubernetes
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 1.0.47 \
  --reuse-values
```

## Next Steps

1. **Production Deployment**
   - Deploy to production mini-server
   - Monitor for 24 hours
   - Verify auto-spawn and cleanup

2. **Documentation**
   - Update main README.md
   - Add migration guide for existing users
   - Create video walkthrough

3. **Enhancements**
   - Add Kubernetes support (spawn as Jobs instead of Docker containers)
   - Add audit trail to separate Kafka topic
   - Implement resource limits per cluster

## Related Documentation

- [CONTROL-PLANE-ARCHITECTURE.md](CONTROL-PLANE-ARCHITECTURE.md) - Architecture design
- [AUTO-DISCOVERY-DESIGN.md](AUTO-DISCOVERY-DESIGN.md) - Design alternatives
- [control-plane/README.md](control-plane/README.md) - Control plane documentation

## License

Apache 2.0
