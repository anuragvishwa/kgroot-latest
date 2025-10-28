# KG RCA Agent - Installation Guide

## Version: 1.0.47

Complete installation guide for the Knowledge Graph RCA Agent with multi-tenant support.

---

## Prerequisites

- Kubernetes cluster (1.19+)
- Helm 3.x
- Kafka broker accessible from cluster
- Neo4j database (for graph-builder on server)

---

## Quick Start (3 Commands)

```bash
# 1. Add Helm repositories
helm repo add anuragvishwa https://anuragvishwa.github.io/kgroot-latest/
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 2. Install Prometheus Stack (if not already installed)
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.enabled=false

# 3. Install KG RCA Agent
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 1.0.47 \
  --namespace observability \
  --set client.id="YOUR_CLIENT_ID" \
  --set client.kafka.brokers="YOUR_KAFKA_HOST:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090" \
  --set alertsWebhook.enabled=false \
  --set vector.rawLogsTopic=raw.k8s.logs \
  --set eventExporter.rawTopic=raw.k8s.events
```

**Important:** Replace `YOUR_CLIENT_ID` with a unique identifier for this cluster (e.g., `af-10`, `af-11`, etc.)

---

## Complete Installation Steps

### 1. Install Prometheus Stack

```bash
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set grafana.enabled=false
```

Wait for Prometheus to be ready:
```bash
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=prometheus -n observability --timeout=180s
```

### 2. Install KG RCA Agent

```bash
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 1.0.47 \
  --namespace observability \
  --set client.id="af-10" \
  --set client.kafka.brokers="98.90.147.12:9092" \
  --set stateWatcher.prometheusUrl="http://kube-prometheus-stack-prometheus.observability.svc:9090" \
  --set alertsWebhook.enabled=false \
  --set vector.rawLogsTopic=raw.k8s.logs \
  --set eventExporter.rawTopic=raw.k8s.events
```

Wait for all pods:
```bash
kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=kg-rca-agent -n observability --timeout=180s
```

### 3. Configure Alertmanager (Optional)

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

# Restart Alertmanager to apply config
kubectl delete pod alertmanager-kube-prometheus-stack-alertmanager-0 -n observability
```

### 4. Install Bug Lab (Optional - for testing)

```bash
helm install bugs anuragvishwa/bugs --namespace buglab --create-namespace
```

---

## Verification

### Check All Pods Running

```bash
kubectl get pods -n observability
```

Expected output:
```
NAME                                                        READY   STATUS
kg-rca-agent-kg-rca-agent-alert-receiver-xxx                1/1     Running
kg-rca-agent-kg-rca-agent-event-exporter-xxx                1/1     Running
kg-rca-agent-kg-rca-agent-state-watcher-xxx                 1/1     Running
kg-rca-agent-kg-rca-agent-vector-xxx                        1/1     Running
```

### Check Event-Exporter Logs

```bash
kubectl logs -n observability -l component=event-exporter --tail=20
```

Should see events being sent to Kafka.

### Check State-Watcher Logs

```bash
kubectl logs -n observability -l component=state-watcher --tail=20
```

Should see resources being watched and sent to Kafka.

---

## Architecture

### Data Flow

```
Kubernetes Cluster (Client)
├── Event-Exporter → events.normalized + raw.k8s.events
├── State-Watcher → state.k8s.resource + state.k8s.topology
├── Vector (DaemonSet) → logs.normalized + raw.k8s.logs
└── Alert-Receiver → alerts.raw + raw.prom.alerts
                ↓
            Kafka Broker
                ↓
        Graph-Builder (Server)
                ↓
            Neo4j Database
```

### Kafka Topics

| Topic | Purpose | Producer |
|-------|---------|----------|
| `events.normalized` | Kubernetes events | event-exporter |
| `logs.normalized` | Container logs | vector |
| `state.k8s.resource` | Resource state | state-watcher |
| `state.k8s.topology` | Resource relationships | state-watcher |
| `alerts.raw` | Prometheus alerts | alert-receiver |
| `raw.k8s.events` | Raw K8s events (archival) | event-exporter |
| `raw.k8s.logs` | Raw logs (archival) | vector |
| `raw.prom.alerts` | Raw alerts (archival) | alert-receiver |

---

## Multi-Tenant Configuration

The system supports multiple Kubernetes clusters sending data to the same Kafka topics.

### Client-Side (Kubernetes)

Each cluster needs a unique `client.id`:
```bash
--set client.id="af-10"  # Cluster 1
--set client.id="af-11"  # Cluster 2
--set client.id="af-12"  # Cluster 3
```

### Server-Side (Graph-Builder)

Each cluster gets its own graph-builder instance with matching `CLIENT_ID`:

```yaml
# docker-compose.yml on mini-server
kg-graph-builder-af-10:
  image: anuragvishwa/kg-graph-builder:1.0.20
  environment:
    CLIENT_ID: "af-10"
    KAFKA_BROKERS: "kafka:9092"
    NEO4J_URI: "bolt://neo4j:7687"

kg-graph-builder-af-11:
  image: anuragvishwa/kg-graph-builder:1.0.20
  environment:
    CLIENT_ID: "af-11"
    KAFKA_BROKERS: "kafka:9092"
    NEO4J_URI: "bolt://neo4j:7687"
```

The graph-builder automatically adds `client_id` to all events/resources that don't have it.

---

## Upgrade

To upgrade to a new version:

```bash
helm repo update
helm upgrade kg-rca-agent anuragvishwa/kg-rca-agent \
  --version 1.0.47 \
  --namespace observability \
  --reuse-values
```

---

## Configuration Options

### Essential Settings

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `client.id` | Unique cluster identifier | `""` | **Yes** |
| `client.kafka.brokers` | Kafka broker address | `""` | **Yes** |
| `stateWatcher.prometheusUrl` | Prometheus URL | `""` | **Yes** |

### Optional Settings

| Parameter | Description | Default |
|-----------|-------------|---------|
| `vector.rawLogsTopic` | Raw logs archival topic | `""` (disabled) |
| `eventExporter.rawTopic` | Raw events archival topic | `""` (disabled) |
| `alertsWebhook.enabled` | Enable alert webhook receiver | `true` |
| `alertsWebhook.rawTopic` | Raw alerts archival topic | `raw.prom.alerts` |

---

## Troubleshooting

### Event-Exporter CrashLoopBackOff

Check logs:
```bash
kubectl logs -n observability -l component=event-exporter
```

Common issues:
- Invalid Kafka broker address
- Network connectivity to Kafka
- YAML syntax errors in config

### No Events in Kafka Topics

1. Check event-exporter is running:
   ```bash
   kubectl get pods -n observability -l component=event-exporter
   ```

2. Check Kafka connectivity:
   ```bash
   kubectl exec -n observability deployment/kg-rca-agent-kg-rca-agent-event-exporter -- nc -zv YOUR_KAFKA_HOST 9092
   ```

3. Trigger test events:
   ```bash
   kubectl run test-pod --image=nginx --restart=Never
   ```

### Missing client_id in Neo4j

Events without `client_id` in JSON will automatically inherit the graph-builder's `CLIENT_ID` environment variable. Ensure the graph-builder is configured correctly on the server side.

---

## Support

- GitHub: https://github.com/anuragvishwa/kgroot-latest
- Issues: https://github.com/anuragvishwa/kgroot-latest/issues

---

## Version History

### v1.0.47 (Current)
- Events sent without client_id in body
- Graph-builder uses CLIENT_ID env var as fallback
- Multi-tenant support via graph-builder fallback
- Clean event JSON without layout modifications

### v1.0.45-1.0.46
- Attempted various layout configurations (deprecated)

### v1.0.39-1.0.44
- Added raw topics support
- Fixed event-exporter routing and templates
- Various bug fixes

---

## License

Apache 2.0
