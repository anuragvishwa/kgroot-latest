# Quick Client Installation Guide

## KGroot RCA Agent v2.1.0 - Client Installation

This guide helps you install the KGroot RCA agent in any Kubernetes cluster to send observability data to the central control plane.

## Prerequisites

- Kubernetes cluster (any cloud provider or on-prem)
- `kubectl` configured
- `helm` installed (v3+)
- Cluster name (must be unique)

## Installation Steps

### Step 1: Add Helm Repositories

```bash
helm repo add anuragvishwa https://anuragvishwa.github.io/kgroot-latest/client-light/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

### Step 2: Install Prometheus (if not already installed)

```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.enabled=false

# Wait for Prometheus to be ready
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=prometheus \
  -n observability \
  --timeout=180s
```

### Step 3: Install KGroot RCA Agent v2.1.0

**⚠️ IMPORTANT**: Change `client.id` to a unique value for your cluster!

```bash
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.1.0 \
  --namespace observability \
  --set client.id="YOUR-UNIQUE-CLUSTER-ID" \
  --set cluster.name="YOUR-CLUSTER-NAME" \
  --set cluster.region="us-west-2" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090"
```

#### Example Values:
- `client.id`: `production-us-west`, `staging-eu-central`, `dev-team-a`
- `cluster.name`: `Production US West`, `Staging EU`, `Dev Team A`
- `cluster.region`: `us-west-2`, `eu-central-1`, `ap-south-1`

### Step 4: Verify Installation

```bash
# Check all pods are running
kubectl get pods -n observability

# Expected pods:
# - kg-rca-agent-state-watcher-*
# - kg-rca-agent-event-exporter-*
# - kg-rca-agent-vector-*
# - kube-prometheus-stack-prometheus-*
# - kube-prometheus-stack-operator-*

# Check registration job succeeded
kubectl get jobs -n observability | grep registry

# Check heartbeat CronJob
kubectl get cronjobs -n observability | grep heartbeat
```

### Step 5: Verify Control Plane Integration

On the **control plane server** (98.90.147.12):

```bash
# SSH to control plane server
ssh ubuntu@98.90.147.12

# Check control plane logs
docker logs kg-control-plane --tail 50

# You should see:
# 📋 New client registered: YOUR-UNIQUE-CLUSTER-ID
# 🚀 Spawning containers for client: YOUR-UNIQUE-CLUSTER-ID
# ✅ Spawned event normalizer: kg-event-normalizer-YOUR-UNIQUE-CLUSTER-ID
# ✅ Spawned log normalizer: kg-log-normalizer-YOUR-UNIQUE-CLUSTER-ID
# ✅ Spawned graph builder: kg-graph-builder-YOUR-UNIQUE-CLUSTER-ID

# Check spawned containers
docker ps | grep YOUR-UNIQUE-CLUSTER-ID

# You should see 3 containers running
```

## What Happens After Installation?

1. **Registration** (Post-install hook):
   - Job publishes to `cluster.registry` Kafka topic
   - Control plane detects new client
   - Auto-spawns 3 containers for your cluster

2. **Heartbeat** (Every minute):
   - CronJob sends heartbeat to `cluster.heartbeat`
   - Keeps your containers alive
   - If no heartbeat for 2 minutes → auto-cleanup

3. **Data Collection**:
   - **Event Exporter**: Watches K8s events → `raw.k8s.events`
   - **Vector**: Collects container logs → `raw.k8s.logs`
   - **State Watcher**: Snapshots cluster state → `state.k8s.resource`

4. **Processing** (On control plane):
   - Event Normalizer: `raw.k8s.events` → `events.normalized`
   - Log Normalizer: `raw.k8s.logs` → `logs.normalized`
   - Graph Builder: Builds fault propagation graphs in Neo4j

## Testing RCA

### Send a test alert:

```bash
# From control plane server
curl -X POST http://localhost:8081/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "PodCrashLooping",
          "severity": "critical",
          "pod": "payment-service",
          "namespace": "production",
          "cluster": "YOUR-UNIQUE-CLUSTER-ID"
        },
        "annotations": {
          "summary": "Pod is crash looping"
        },
        "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
      }
    ]
  }'

# Check RCA webhook logs
docker logs kg-rca-webhook --tail 50
```

## Accessing Dashboards

- **Kafka UI**: http://98.90.147.12:7777
- **Neo4j Browser**: http://98.90.147.12:7474
  - Username: `neo4j`
  - Password: `Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA`

## Troubleshooting

### Pods not starting?

```bash
kubectl describe pod <pod-name> -n observability
kubectl logs <pod-name> -n observability
```

### Registration failed?

```bash
kubectl logs job/kg-rca-agent-registry -n observability
```

### No data in control plane?

```bash
# Check if containers are spawned
docker ps | grep YOUR-UNIQUE-CLUSTER-ID

# Check normalizer logs
docker logs kg-event-normalizer-YOUR-UNIQUE-CLUSTER-ID
docker logs kg-log-normalizer-YOUR-UNIQUE-CLUSTER-ID
```

### Heartbeat not working?

```bash
kubectl logs cronjob/kg-rca-agent-heartbeat -n observability
```

## Uninstallation

```bash
# This will also trigger cleanup on control plane
helm uninstall kg-rca-agent -n observability

# On control plane, containers will auto-cleanup after 2 minutes (no heartbeat)
```

## Next Steps

1. Install bug scenarios for testing:
   ```bash
   helm install bugs anuragvishwa/bugs --namespace buglab --create-namespace
   ```

2. Configure Alertmanager webhook to send alerts to control plane

3. View fault graphs in Neo4j browser

4. Monitor RCA accuracy and patterns

## Support

- Issues: https://github.com/anuragvishwa/kgroot-latest/issues
- Documentation: https://github.com/anuragvishwa/kgroot-latest

---

**📊 Expected Accuracy**: 85-95% top-3 root cause identification
**🚀 Architecture**: 13-topic Control Plane V2 with per-client isolation
