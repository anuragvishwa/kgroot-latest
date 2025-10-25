# KGroot RCA - Client Helm Chart Deployment

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client's Kubernetes Cluster                  │
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                 │
│  │  kg-rca-agent    │    │  Prometheus      │                 │
│  │  ----------------│    │  Stack           │                 │
│  │  • State Watcher │    │                  │                 │
│  │  • Event Export  │    │  Alertmanager───┼────┐            │
│  │  • Vector Logs   │    │                  │    │            │
│  │  • Alert Receiver│◄───┘                  │    │            │
│  └────────┬─────────┘    └──────────────────┘    │            │
│           │                                       │            │
│           │ Sends to Kafka                   Webhook POST     │
│           │                                       │            │
└───────────┼───────────────────────────────────────┼────────────┘
            │                                       │
            │                                       │
            ▼                                       ▼
┌───────────────────────────────────────────────────────────────────┐
│                    Your Server (Docker Compose)                   │
│                                                                   │
│  ┌─────────────┐    ┌──────────────────┐   ┌────────────────┐  │
│  │   Kafka     │    │  kg-rca-webhook  │   │   Neo4j        │  │
│  │   :9092     │◄───│      :8081       │──▶│   :7474/7687   │  │
│  └─────────────┘    └──────────────────┘   └────────────────┘  │
│         │                     │                                   │
│         │                     ▼                                   │
│         │            ┌──────────────────┐                         │
│         └───────────▶│  Control Plane   │                         │
│                      │  Graph Builders  │                         │
│                      └──────────────────┘                         │
└───────────────────────────────────────────────────────────────────┘
```

---

## 📦 Deployment Options

### **Option 1: Webhook Only (Recommended - Simple)**
- Client only sends Alertmanager webhooks
- No Kafka needed on client side
- Easiest to set up
- See: [CLIENT-ONBOARDING.md](CLIENT-ONBOARDING.md)

### **Option 2: Full Observability with Kafka (Advanced)**
- Client deploys kg-rca-agent Helm chart
- Sends logs, events, metrics to your Kafka
- Enables advanced pattern learning
- Provides richer context for RCA

---

## 🚀 Option 2: Full Helm Deployment

### Prerequisites

**On Client's Cluster:**
- Kubernetes 1.19+
- Helm 3.0+
- kubectl configured

**On Your Server:**
- Kafka accessible at `98.90.147.12:9092`
- Kafka topics created (see below)

---

## Step 1: Create Kafka Topics (On Your Server)

```bash
# On your Ubuntu server
cd ~/kgroot-latest/mini-server-prod

# Create required topics
docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:29092 \
  --create --topic cluster.registry --partitions 3 --replication-factor 1 \
  --config cleanup.policy=compact

docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:29092 \
  --create --topic cluster.heartbeat --partitions 3 --replication-factor 1 \
  --config retention.ms=3600000

docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:29092 \
  --create --topic raw.k8s.events --partitions 3 --replication-factor 1

docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:29092 \
  --create --topic raw.k8s.logs --partitions 3 --replication-factor 1

# Verify topics created
docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:29092 --list
```

---

## Step 2: Client Helm Installation

### Send to Client:

```bash
# ============================================
# KG RCA Agent Installation
# Client-Side Deployment
# ============================================

# 1. Add Helm repositories
helm repo add anuragvishwa https://anuragvishwa.github.io/kgroot-latest/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 2. Install Prometheus stack (if not already installed)
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.enabled=false

# Wait for Prometheus
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=prometheus \
  -n observability \
  --timeout=180s

# 3. Install KG RCA Agent
# ⚠️ IMPORTANT: Change these values!
#   - client.id: Unique ID for this cluster (e.g., "client-prod-us-east")
#   - cluster.name: Human-readable name
#   - client.kafka.brokers: Your Kafka server IP
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.2 \
  --namespace observability \
  --set client.id="CLIENT_ID_HERE" \
  --set cluster.name="production-us-east" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090" \
  --set alertsWebhook.enabled=true \
  --set alertsWebhook.url="http://98.90.147.12:8081/webhook" \
  --set vector.rawLogsTopic=raw.k8s.logs \
  --set eventExporter.rawTopic=raw.k8s.events

# 4. Wait for pods to be ready
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/instance=kg-rca-agent \
  -n observability \
  --timeout=180s

# 5. Verify installation
kubectl get pods -n observability -l app.kubernetes.io/instance=kg-rca-agent
```

---

## Step 3: Configure Alertmanager

```bash
# Update Alertmanager to send to BOTH webhook AND alert-receiver
kubectl create secret generic alertmanager-kube-prometheus-stack-alertmanager \
  --from-literal=alertmanager.yaml="$(cat <<'EOF'
global:
  resolve_timeout: 5m

receivers:
  - name: "null"

  - name: "kg-rca-combined"
    webhook_configs:
      # Send to your central RCA webhook
      - url: "http://98.90.147.12:8081/webhook"
        send_resolved: true
      # Also send to local alert-receiver (for Kafka)
      - url: "http://kg-rca-agent-kg-rca-agent-alert-receiver.observability.svc:9093/webhook"
        send_resolved: true

route:
  group_by: [namespace, alertname]
  group_interval: 5m
  group_wait: 30s
  receiver: "kg-rca-combined"
  repeat_interval: 12h
  routes:
    - matchers:
        - alertname = "Watchdog"
      receiver: "null"
EOF
)" \
  --namespace observability \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart Alertmanager
kubectl delete pod alertmanager-kube-prometheus-stack-alertmanager-0 -n observability
```

---

## Step 4: Verify Data Flow

### On Client Cluster:

```bash
# Check all components are running
kubectl get pods -n observability

# Expected pods:
# - kg-rca-agent-state-watcher-*
# - kg-rca-agent-event-exporter-*
# - kg-rca-agent-vector-*
# - kg-rca-agent-alert-receiver-*

# Check state-watcher logs (sends heartbeats)
kubectl logs -n observability -l app=state-watcher --tail=20

# Check event-exporter logs (sends K8s events)
kubectl logs -n observability -l app=event-exporter --tail=20

# Check vector logs (sends logs to Kafka)
kubectl logs -n observability -l app=vector --tail=20
```

### On Your Server:

```bash
# Check Kafka is receiving data
# Cluster registry (one-time registration)
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.registry \
  --from-beginning \
  --max-messages 5

# Heartbeats (every 30s)
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.heartbeat \
  --max-messages 5

# K8s events
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic raw.k8s.events \
  --max-messages 5

# Check control plane spawned graph-builder
docker ps | grep graph-builder
# Should see: kg-graph-builder-CLIENT_ID_HERE

# Check webhook is receiving alerts
docker logs -f kg-rca-webhook | grep "Received webhook"
```

---

## 🧪 Testing

### Generate Test Alerts on Client Cluster:

```bash
# Option 1: Install bugs chart (test scenarios)
helm install bugs anuragvishwa/bugs \
  --namespace buglab \
  --create-namespace

# Wait a bit for bugs to trigger alerts
kubectl get pods -n buglab

# Option 2: Manually create a pod that will OOM
kubectl run oom-test --image=polinux/stress --namespace=default \
  --restart=Never \
  --limits='memory=50Mi' \
  --requests='memory=25Mi' \
  -- stress --vm 1 --vm-bytes 100M

# Watch for alerts in Prometheus
kubectl port-forward -n observability svc/kube-prometheus-stack-prometheus 9090:9090

# Open browser: http://localhost:9090/alerts
```

### Verify RCA on Your Server:

```bash
# Watch webhook receive and analyze alerts
docker logs -f kg-rca-webhook

# You should see:
# 📥 Received webhook: 1 alerts, status=firing
# 🔍 Triggering RCA for 3 alerts
# 🎯 Top Root Causes...
# 💥 Blast Radius...
# 📋 Top 3 Solutions...
```

---

## 📊 What Gets Sent to Your Server

### Via Webhook (Immediate):
- ✅ Prometheus alerts (critical/warning)
- ✅ Trigger RCA analysis
- ✅ Get immediate recommendations

### Via Kafka (Background):
- ✅ K8s events (pod restarts, OOM, scheduling failures)
- ✅ Resource metrics (CPU, memory, disk)
- ✅ Application logs
- ✅ Cluster heartbeats

### Processed by Control Plane:
- ✅ Graph-builder creates knowledge graphs
- ✅ Patterns stored in Neo4j
- ✅ Historical analysis improves over time

---

## 🔧 Configuration Options

### Customize Helm Values:

```yaml
# values.yaml
client:
  id: "my-cluster-id"  # Unique per cluster
  kafka:
    brokers: "98.90.147.12:9092"

cluster:
  name: "production-us-east"

alertsWebhook:
  enabled: true
  url: "http://98.90.147.12:8081/webhook"

stateWatcher:
  enabled: true
  prometheusUrl: "http://prometheus.observability.svc:9090"
  heartbeatInterval: 30s

eventExporter:
  enabled: true
  rawTopic: "raw.k8s.events"

vector:
  enabled: true
  rawLogsTopic: "raw.k8s.logs"
```

```bash
# Install with custom values
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.2 \
  --namespace observability \
  --values values.yaml
```

---

## 🔄 Upgrading

```bash
# Update repo
helm repo update

# Upgrade agent
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 2.0.2 \
  --namespace observability \
  --reuse-values
```

---

## 🗑️ Uninstalling

```bash
# On client cluster
helm uninstall kg-rca-agent --namespace observability

# On your server (auto-cleanup happens via control plane)
# Graph-builder for this client will be removed automatically
# after 5 minutes of no heartbeats

# Manual cleanup if needed
docker ps | grep graph-builder
docker stop kg-graph-builder-CLIENT_ID
docker rm kg-graph-builder-CLIENT_ID
```

---

## 🆚 Comparison: Webhook vs Full Helm

| Feature | Webhook Only | Full Helm |
|---------|-------------|-----------|
| Setup Time | 5 minutes | 15 minutes |
| Client Requirements | Just Alertmanager | Full k8s cluster |
| Data Sent | Alerts only | Alerts + Events + Logs |
| RCA Accuracy | 75-80% | 85-90% |
| Pattern Learning | No | Yes |
| Historical Analysis | Limited | Full |
| Client Complexity | Very Low | Medium |
| Best For | Quick start | Production use |

---

## 📞 Support

**Issues?**
- Check [TROUBLESHOOTING-PLAYBOOK.md](../docs/TROUBLESHOOTING-PLAYBOOK.md)
- Review Helm chart docs: https://github.com/anuragvishwa/kgroot-latest
- Contact support

---

## 🎯 Next Steps

1. **Choose deployment option**: Webhook (simple) or Helm (full)
2. **For Helm**: Create Kafka topics on your server
3. **Send client the install commands** with your IP/Kafka address
4. **Verify data flow** (Kafka consumers, webhook logs)
5. **Test RCA** with bug scenarios
6. **Monitor and improve** patterns over time

---

**Your KGroot RCA system supports both simple webhook integration AND full Helm-based observability!** 🚀
