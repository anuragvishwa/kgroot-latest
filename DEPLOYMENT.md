# Deployment Guide

This guide covers deploying the Kubernetes RCA (Root Cause Analysis) system on a clean Minikube cluster.

## Architecture Overview

The system consists of:
- **Kafka**: Message broker for events, logs, and alerts
- **Vector**: Data collection and normalization pipeline
- **Prometheus + Alertmanager**: Metrics and alerting
- **K8s Event Exporter**: Kubernetes event forwarding
- **State Watcher**: Kubernetes state tracking
- **Alerts Enricher**: Alert enrichment service
- **Graph Builder**: Knowledge graph builder (Neo4j)

## Prerequisites

- Minikube (v1.30+)
- kubectl
- Helm 3
- At least 8GB RAM allocated to Minikube

## Quick Start (Clean Cluster)

### 1. Start Minikube

```bash
minikube start --cpus=4 --memory=8192 --driver=docker
```

### 2. Create Namespace

```bash
kubectl create namespace observability
kubectl create namespace monitoring
```

### 3. Deploy Kafka

```bash
kubectl apply -f k8s/kafka.yaml
```

Wait for Kafka to be ready:
```bash
kubectl wait --for=condition=ready pod/kafka-0 -n observability --timeout=300s
```

### 4. Initialize Kafka Topics

The kafka-init Job will automatically run and create all required topics. Verify:

```bash
kubectl logs -n observability job/kafka-init
kubectl get job -n observability
```

Expected topics:
- `raw.k8s.logs` - Raw Kubernetes logs
- `raw.k8s.events` - Raw Kubernetes events
- `raw.prom.alerts` - Raw Prometheus alerts
- `raw.events` - Combined raw events
- `events.normalized` - Normalized events (alerts + k8s events)
- `logs.normalized` - Normalized logs
- `alerts.normalized` - Normalized Prometheus alerts only
- `alerts.enriched` - Enriched alerts with context
- `state.k8s.resource` - Kubernetes resource state (compacted)
- `state.k8s.topology` - Kubernetes topology (compacted)
- `state.prom.rules` - Prometheus rules state (compacted)
- `state.prom.targets` - Prometheus targets state (compacted)
- `graph.commands` - Graph update commands (compacted)
- `dlq.raw` - Dead letter queue for raw events
- `dlq.normalized` - Dead letter queue for normalized events

### 5. Install Prometheus Stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f k8s/prom-values.yaml \
  --wait
```

### 6. Deploy Vector Pipeline

```bash
kubectl apply -f k8s/vector-configmap.yaml
```

Wait for Vector pods:
```bash
kubectl wait --for=condition=ready pod -l app=vector -n observability --timeout=120s
kubectl wait --for=condition=ready pod -l app=vector-logs -n observability --timeout=120s
```

### 7. Deploy K8s Event Exporter

```bash
kubectl apply -f k8s/k8s-event-exporter.yaml
```

### 8. Deploy State Watcher

```bash
kubectl apply -f k8s/state-watcher.yaml
```

### 9. Deploy Alerts Enricher

```bash
# Build and deploy the alerts-enricher
cd alerts-enricher
docker build -t alerts-enricher:latest .
minikube image load alerts-enricher:latest

kubectl apply -f k8s/alerts-enricher.yaml
```

### 10. Optional: Deploy Test Alert

```bash
kubectl apply -f k8s/always-firing-rule.yaml
```

## Accessing UIs

### Kafka UI

```bash
# Using NodePort
minikube service kafka-ui -n observability

# Or port-forward
kubectl port-forward -n observability svc/kafka-ui 8080:8080
# Access at http://localhost:8080
```

### Prometheus

```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
# Access at http://localhost:9090
```

### Grafana

```bash
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
# Access at http://localhost:3000
# Default credentials: admin / prom-operator
```

### Alertmanager

```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-alertmanager 9093:9093
# Access at http://localhost:9093
```

## Verification

### 1. Check All Pods are Running

```bash
kubectl get pods -n observability
kubectl get pods -n monitoring
```

### 2. Verify Kafka Topics

```bash
kubectl exec -n observability kafka-0 -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
```

### 3. Check Message Flow

Check alerts.normalized:
```bash
kubectl exec -n observability kafka-0 -- sh -c \
  '/opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic alerts.normalized \
  --from-beginning \
  --max-messages 1 2>/dev/null'
```

Check events.normalized:
```bash
kubectl exec -n observability kafka-0 -- sh -c \
  '/opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic events.normalized \
  --from-beginning \
  --max-messages 1 2>/dev/null'
```

Check logs.normalized:
```bash
kubectl exec -n observability kafka-0 -- sh -c \
  '/opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic logs.normalized \
  --from-beginning \
  --max-messages 1 2>/dev/null'
```

### 4. Check Vector Logs

```bash
kubectl logs -n observability deployment/vector --tail=50
kubectl logs -n observability daemonset/vector-logs --tail=50
```

## Data Flow for RCA

### Normalized Event Schema

All normalized events follow this schema:

```json
{
  "etype": "prom.alert | k8s.event | k8s.log",
  "event_id": "unique-uuid",
  "event_time": "ISO8601 timestamp",
  "severity": "INFO | WARNING | ERROR | CRITICAL",
  "reason": "alert/event name",
  "message": "human-readable description",
  "subject": {
    "kind": "Pod | Deployment | Service | ...",
    "ns": "namespace",
    "name": "resource-name",
    "uid": "optional-resource-uid"
  }
}
```

### Topic Usage for RCA

1. **alerts.normalized**: Pure Prometheus alerts, normalized schema
   - Use for: Alert-based RCA, alert correlation
   - Fields: reason, severity, subject, message

2. **events.normalized**: Combined Prometheus alerts + K8s events
   - Use for: Full event timeline, cross-correlation
   - Includes both alert firings and K8s lifecycle events

3. **logs.normalized**: Application and system logs
   - Use for: Log analysis, error pattern detection
   - Fields: message, severity, subject (pod info)

4. **state.k8s.resource**: Current state of K8s resources
   - Use for: Resource state lookup, health checks
   - Compacted topic (latest state only)

5. **state.k8s.topology**: Kubernetes resource relationships
   - Use for: Dependency graph, impact analysis
   - Edges: CONTROLS, SERVES, DEPENDS_ON

6. **state.prom.rules**: Prometheus alerting rules
   - Use for: Alert definition lookup, rule health

7. **alerts.enriched**: Context-enriched alerts
   - Use for: RCA with full context
   - Includes: related resources, topology, metrics

## Troubleshooting

### Kafka Topics Not Created

```bash
# Check kafka-init job
kubectl logs -n observability job/kafka-init

# Manually run if needed
kubectl delete job kafka-init -n observability
kubectl apply -f k8s/kafka.yaml
```

### Vector Not Receiving Alerts

```bash
# Check Alertmanager webhook config
kubectl get secret -n monitoring alertmanager-prometheus-kube-prometheus-alertmanager \
  -o jsonpath='{.data.alertmanager\.yaml}' | base64 -d

# Should show:
# - name: vector-webhook
#   webhook_configs:
#   - url: 'http://vector.observability.svc:9000'
```

### No Messages in Topics

```bash
# Check Vector logs for errors
kubectl logs -n observability deployment/vector | grep -i error

# Test webhook manually
kubectl run test-curl --image=curlimages/curl --rm -i --restart=Never -- \
  sh -c 'curl -X POST http://vector.observability.svc:9000 \
  -H "Content-Type: application/json" \
  -d "{\"alerts\":[{\"status\":\"firing\",\"labels\":{\"alertname\":\"Test\"},\"fingerprint\":\"test\"}]}"'
```

### Kafka Pod Stuck in Pending

```bash
# Check PVC
kubectl get pvc -n observability

# If storage class issues, delete and recreate
kubectl delete statefulset kafka -n observability
kubectl delete pvc data-kafka-0 -n observability
kubectl apply -f k8s/kafka.yaml
```

## Cleanup

```bash
# Delete all resources
kubectl delete -f k8s/kafka.yaml
kubectl delete -f k8s/vector-configmap.yaml
kubectl delete -f k8s/k8s-event-exporter.yaml
kubectl delete -f k8s/state-watcher.yaml
kubectl delete -f k8s/always-firing-rule.yaml
helm uninstall prometheus -n monitoring

# Delete namespaces
kubectl delete namespace observability
kubectl delete namespace monitoring
```

## Production Considerations

1. **High Availability**: Use 3+ Kafka brokers with replication-factor=3
2. **Persistence**: Use proper storage class with backups
3. **Resource Limits**: Tune CPU/memory based on load
4. **Monitoring**: Add Prometheus exporters for Kafka, Vector
5. **Security**: Enable authentication (SASL), encryption (TLS)
6. **Retention**: Adjust topic retention based on requirements
7. **Compaction**: Monitor compaction lag on state topics
