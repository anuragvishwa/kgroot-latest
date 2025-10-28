# Complete Guide: Lightweight Kafka Producer & Installation

## What's New in v2.1.2

✨ **90% smaller image for registry jobs!**
- Replaced `confluentinc/cp-kafka` (500-700MB) with `kafka-producer-minimal` (50-80MB)
- **5-7 minutes faster** deployment times
- Registry and deregister jobs now start quickly

---

## Quick Install (Works Now - No Helm Repo Needed)

If GitHub Pages isn't updated yet, install directly from GitHub:

## Method 1: Install from Local File

```bash
# Download the chart from GitHub
curl -L -o kg-rca-agent-2.1.0.tgz \
  https://github.com/anuragvishwa/kgroot-latest/raw/gh-pages/client-light/kg-rca-agent-2.1.0.tgz

# Install Prometheus (if not already installed)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

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

# Install KGroot RCA Agent v2.1.0 from local file
helm install kg-rca-agent ./kg-rca-agent-2.1.0.tgz \
  --namespace observability \
  --set client.id="YOUR-UNIQUE-CLUSTER-ID" \
  --set cluster.name="YOUR-CLUSTER-NAME" \
  --set cluster.region="us-west-2" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090"
```

## Method 2: Install Directly from GitHub Raw URL

```bash
# Install Prometheus (if needed)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.enabled=false

# Install KGroot RCA Agent directly from GitHub raw URL
helm install kg-rca-agent \
  https://github.com/anuragvishwa/kgroot-latest/raw/gh-pages/client-light/kg-rca-agent-2.1.0.tgz \
  --namespace observability \
  --set client.id="YOUR-UNIQUE-CLUSTER-ID" \
  --set cluster.name="YOUR-CLUSTER-NAME" \
  --set cluster.region="us-west-2" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090"
```

## Example Values

- `client.id`: `production-us-west`, `staging-eu-central`, `dev-team-a`
- `cluster.name`: `Production US West`, `Staging EU`, `Dev Team A`
- `cluster.region`: `us-west-2`, `eu-central-1`, `ap-south-1`

## Verify Installation

```bash
# Check all pods are running
kubectl get pods -n observability

# Expected pods:
# - kg-rca-agent-state-watcher-*
# - kg-rca-agent-event-exporter-*
# - kg-rca-agent-vector-*
# - kube-prometheus-stack-prometheus-*

# Check registration job succeeded
kubectl get jobs -n observability | grep registry

# Check heartbeat CronJob
kubectl get cronjobs -n observability | grep heartbeat
```

## Verify Control Plane Integration

On the control plane server (98.90.147.12):

```bash
# Check control plane logs
docker logs kg-control-plane --tail 50

# You should see:
# 📋 New client registered: YOUR-UNIQUE-CLUSTER-ID
# 🚀 Spawning containers for client: YOUR-UNIQUE-CLUSTER-ID

# Check spawned containers
docker ps | grep YOUR-UNIQUE-CLUSTER-ID

# You should see 3 containers running:
# - kg-event-normalizer-YOUR-UNIQUE-CLUSTER-ID
# - kg-log-normalizer-YOUR-UNIQUE-CLUSTER-ID
# - kg-graph-builder-YOUR-UNIQUE-CLUSTER-ID
```

## After GitHub Pages is Enabled

Once GitHub Pages is working, you can switch to the repository method:

```bash
# Remove the current installation
helm uninstall kg-rca-agent -n observability

# Add the Helm repository
helm repo add anuragvishwa https://anuragvishwa.github.io/kgroot-latest/client-light/
helm repo update

# Reinstall from the repository
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.1.0 \
  --namespace observability \
  --set client.id="YOUR-UNIQUE-CLUSTER-ID" \
  --set cluster.name="YOUR-CLUSTER-NAME" \
  --set cluster.region="us-west-2" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090"
```

---

**Quick Test (Use this now):**

```bash
helm install kg-rca-agent \
  https://github.com/anuragvishwa/kgroot-latest/raw/gh-pages/client-light/kg-rca-agent-2.1.0.tgz \
  --namespace observability \
  --create-namespace \
  --set client.id="test-cluster-$(date +%s)" \
  --set cluster.name="Test Cluster" \
  --set client.kafka.brokers="98.90.147.12:9092"
```
