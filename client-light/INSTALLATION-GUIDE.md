# KG RCA Agent Installation Guide

Complete installation guide for the Knowledge Graph RCA Agent Helm chart.

## Quick Installation

### Option 1: From Helm Repository (Recommended)

The easiest way to install the KG RCA Agent:

```bash
# Add the Helm repository
helm repo add kg-rca-agent https://anuragvishwa.github.io/kgroot-latest/
helm repo update

# Install the chart
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  --set kafka.bootstrapServers="your-kafka-server:9092"
```

### Option 2: From Source

```bash
# Clone the repository
git clone https://github.com/anuragvishwa/kgroot-latest.git
cd kgroot-latest/client-light

# Install from local chart
helm install kg-rca-agent ./helm-chart \
  --namespace observability \
  --create-namespace \
  --set kafka.bootstrapServers="your-kafka-server:9092"
```

## Prerequisites

- **Kubernetes**: 1.19 or higher
- **Helm**: 3.0 or higher
- **Kafka**: Running Kafka cluster for data streaming
- **Permissions**: Cluster admin access to install RBAC resources

## Configuration

### Required Settings

The following settings must be configured for the agent to function:

```yaml
kafka:
  bootstrapServers: "your-kafka-server:9092"  # Required: Your Kafka broker(s)

  # Optional: Configure SSL if using secure Kafka
  ssl:
    enabled: false
    # caSecret: "kafka-ca-cert"
    # certSecret: "kafka-client-cert"
```

### Recommended Production Settings

Create a `values.yaml` file with your production configuration:

```yaml
# Production values.yaml
kafka:
  bootstrapServers: "kafka.production.svc.cluster.local:9092"
  ssl:
    enabled: true
    caSecret: "kafka-ca-cert"
    certSecret: "kafka-client-cert"

# Resource limits for production workloads
vector:
  resources:
    requests:
      cpu: "200m"
      memory: "256Mi"
    limits:
      cpu: "500m"
      memory: "512Mi"

alertReceiver:
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "200m"
      memory: "256Mi"

stateWatcher:
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "200m"
      memory: "256Mi"

eventExporter:
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
    limits:
      cpu: "200m"
      memory: "256Mi"
```

Install with custom values:

```bash
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  --values values.yaml
```

## Advanced Configuration

### Kafka Topics

The agent publishes data to these Kafka topics:

```yaml
topics:
  logs: "logs.normalized"           # Pod logs
  events: "events.normalized"       # Kubernetes events
  alerts: "alerts.normalized"       # Prometheus alerts
  stateNode: "state.k8s.node"      # Node state
  statePod: "state.k8s.pod"        # Pod state
  stateService: "state.k8s.service" # Service state
```

Override default topics:

```bash
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --set topics.logs="custom.logs" \
  --set topics.events="custom.events"
```

### Prometheus Integration

To enable alert collection from Prometheus/Alertmanager:

```yaml
alertReceiver:
  enabled: true
  service:
    type: ClusterIP
    port: 8080
```

Configure Alertmanager to send alerts:

```yaml
# alertmanager.yml
receivers:
  - name: 'kg-rca-agent'
    webhook_configs:
      - url: 'http://kg-rca-agent-alert-receiver.observability.svc.cluster.local:8080/api/v1/alerts'
        send_resolved: true

route:
  receiver: 'kg-rca-agent'
```

### Monitoring Specific Namespaces

By default, the agent monitors all namespaces. To monitor specific namespaces:

```yaml
namespaceFilter:
  enabled: true
  namespaces:
    - production
    - staging
```

### SSL/TLS for Kafka

For secure Kafka connections:

1. Create secrets with your certificates:

```bash
kubectl create secret generic kafka-ca-cert \
  --from-file=ca.crt=path/to/ca.crt \
  -n observability

kubectl create secret generic kafka-client-cert \
  --from-file=client.crt=path/to/client.crt \
  --from-file=client.key=path/to/client.key \
  -n observability
```

2. Enable SSL in values:

```yaml
kafka:
  ssl:
    enabled: true
    caSecret: "kafka-ca-cert"
    certSecret: "kafka-client-cert"
```

## Verification

### Check Installation Status

```bash
# Check all pods are running
kubectl get pods -n observability

# Expected output:
# NAME                                         READY   STATUS    RESTARTS
# kg-rca-agent-alert-receiver-xxx              1/1     Running   0
# kg-rca-agent-event-exporter-xxx              1/1     Running   0
# kg-rca-agent-state-watcher-xxx               1/1     Running   0
# kg-rca-agent-vector-xxx                      1/1     Running   0
```

### Verify Data Collection

Check logs to ensure data is flowing:

```bash
# Check Vector logs (should show Kafka sink activity)
kubectl logs -n observability -l component=vector --tail=50

# Check Event Exporter logs
kubectl logs -n observability -l component=event-exporter --tail=50

# Check State Watcher logs
kubectl logs -n observability -l component=state-watcher --tail=50

# Check Alert Receiver logs
kubectl logs -n observability -l component=alert-receiver --tail=50
```

### Verify Kafka Topics

If you have Kafka access, verify data is being published:

```bash
# List topics (should see kg-* topics)
kafka-topics.sh --bootstrap-server your-kafka:9092 --list

# Consume from a topic to verify data
kafka-console-consumer.sh \
  --bootstrap-server your-kafka:9092 \
  --topic events.normalized \
  --from-beginning \
  --max-messages 5
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod -n observability <pod-name>

# Common issues:
# - ImagePullBackOff: Check image availability
# - CrashLoopBackOff: Check logs for startup errors
# - Pending: Check resource availability and node capacity
```

### No Data in Kafka

```bash
# 1. Verify Kafka connectivity
kubectl exec -n observability <vector-pod> -- \
  nc -zv your-kafka-server 9092

# 2. Check Vector configuration
kubectl get configmap -n observability kg-rca-agent-vector-config -o yaml

# 3. Verify RBAC permissions
kubectl auth can-i list pods --as=system:serviceaccount:observability:kg-rca-agent
```

### High Memory Usage

Adjust resource limits and Vector buffer settings:

```yaml
vector:
  resources:
    limits:
      memory: "1Gi"  # Increase if needed
  bufferMaxEvents: 5000  # Reduce if memory constrained
```

## Upgrading

### Upgrade to Latest Version

```bash
# Update Helm repository
helm repo update

# Upgrade release
helm upgrade kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --reuse-values
```

### Upgrade with New Values

```bash
helm upgrade kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --values new-values.yaml
```

## Uninstalling

```bash
# Remove the Helm release
helm uninstall kg-rca-agent --namespace observability

# (Optional) Delete the namespace
kubectl delete namespace observability
```

## Support

- **Documentation**: https://github.com/anuragvishwa/kgroot-latest
- **Issues**: https://github.com/anuragvishwa/kgroot-latest/issues
- **Example Values**: [example-values.yaml](./example-values.yaml)

## Next Steps

1. [Configure Alertmanager integration](./ALERTMANAGER-FIX.md)
2. [View deployment status](./DEPLOYMENT-STATUS.md)
3. [Review changelog](./CHANGELOG.md)
4. Set up the server-side components (Kafka, Neo4j, Graph Builder)
