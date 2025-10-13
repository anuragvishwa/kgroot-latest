# KG RCA Agent - Client Installation

Lightweight Kubernetes agent that streams events, logs, and resource state to the KG RCA Server for real-time root cause analysis.

## What It Does

Installs these components in your Kubernetes cluster:
- **Vector DaemonSet**: Collects and normalizes pod logs
- **Event Exporter**: Captures Kubernetes events (pod crashes, scheduling issues, etc.)
- **State Watcher**: Monitors resource state and topology changes
- **Prometheus Agent** (optional): Sends metrics to server

All data is sent to your KG RCA Server via Kafka.

## Prerequisites

- Kubernetes 1.20+
- Helm 3.x
- `kubectl` configured with cluster access
- KG RCA Server URL and credentials from your administrator

## Quick Start

### 1. Get Server Connection Details

From your KG RCA Server administrator, get:
- **Kafka Bootstrap Server**: `kafka.yourcompany.com:9092` (or IP:port)
- **Client ID**: Unique identifier for your cluster (e.g., `prod-us-west-2`)
- **API Key**: Authentication token (if required)

### 2. Create Values File

```bash
cat > my-values.yaml <<EOF
client:
  # Unique identifier for this cluster
  id: "my-cluster-prod"

  # API key (if server requires authentication)
  apiKey: ""

  # Kafka connection
  kafka:
    # Replace with your server's Kafka endpoint
    bootstrapServers: "3.93.235.47:9092"

    # For SSL (production):
    # bootstrapServers: "kafka.yourcompany.com:9093"
    # sasl:
    #   enabled: true
    #   mechanism: SCRAM-SHA-512
    #   username: "my-cluster-prod"
    #   password: "your-password"

# Optional: Limit monitoring to specific namespaces
# monitoredNamespaces: ["production", "staging"]

# Components (all enabled by default)
stateWatcher:
  enabled: true

vector:
  enabled: true

eventExporter:
  enabled: true

prometheusAgent:
  enabled: false  # Set to true if you want to send metrics
EOF
```

### 3. Install Helm Chart

```bash
# Add Helm repository (once available)
# helm repo add lumniverse https://charts.lumniverse.com
# helm repo update

# For now, use local chart
helm install kg-rca-agent ./helm-chart/kg-rca-agent \
  --values my-values.yaml \
  --namespace observability \
  --create-namespace
```

### 4. Verify Installation

```bash
# Check pods are running
kubectl get pods -n observability

# Expected output:
# NAME                                READY   STATUS    RESTARTS   AGE
# kg-rca-agent-vector-xxxxx          1/1     Running   0          30s
# kg-rca-agent-event-exporter-xxx    1/1     Running   0          30s
# kg-rca-agent-state-watcher-xxx     1/1     Running   0          30s

# Check Vector is sending logs
kubectl logs -n observability -l app=vector --tail=50

# Check Event Exporter is capturing events
kubectl logs -n observability -l app=event-exporter --tail=50
```

### 5. Verify Data on Server

On your KG RCA Server, verify data is arriving:

```bash
# SSH to server
ssh your-server

# Check Kafka topics for your client data
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic events.normalized \
  --max-messages 5

# Check Neo4j for your cluster's resources
docker exec kg-neo4j cypher-shell -u neo4j -p <password> \
  "MATCH (n:Pod) RETURN n.name, n.namespace LIMIT 10"
```

## Configuration Options

### Minimal Configuration (Testing)

```yaml
client:
  id: "test-cluster"
  kafka:
    bootstrapServers: "server-ip:9092"
```

### Production Configuration (SSL + Authentication)

```yaml
client:
  id: "prod-cluster-001"
  apiKey: "prod-api-key-xyz"

  kafka:
    bootstrapServers: "kafka.company.com:9093"
    sasl:
      enabled: true
      mechanism: SCRAM-SHA-512
      username: "prod-cluster-001"
      password: "secure-password"

  monitoredNamespaces: ["production", "critical-apps"]

vector:
  enabled: true
  resources:
    requests:
      memory: 256Mi
      cpu: 100m
    limits:
      memory: 512Mi
      cpu: 500m

eventExporter:
  enabled: true

stateWatcher:
  enabled: true
```

### Component Details

#### Vector (Log Collection)
- Runs as DaemonSet on every node
- Collects logs from all pods (or specified namespaces)
- Normalizes log format
- Sends to: `events.normalized` Kafka topic

#### Event Exporter
- Watches Kubernetes Event API
- Captures pod failures, scheduling issues, etc.
- Sends to: `events.normalized` Kafka topic

#### State Watcher
- Monitors resource state (Pod, Deployment, Service, etc.)
- Tracks topology relationships
- Sends to: `state.k8s.resource` and `state.k8s.topology` topics

#### Prometheus Agent (Optional)
- Scrapes metrics from your cluster
- Forwards to server's Prometheus
- Enables metric-based alerting

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod -n observability <pod-name>

# Common issues:
# - ImagePullBackOff: Check image repository access
# - CrashLoopBackOff: Check logs with `kubectl logs`
```

### No Data Reaching Server

```bash
# Check Vector logs
kubectl logs -n observability -l app=vector --tail=100

# Check Kafka connectivity from pod
kubectl exec -n observability -it \
  $(kubectl get pod -n observability -l app=vector -o name | head -1) \
  -- nc -zv <server-ip> 9092

# Check for network policies blocking egress
kubectl get networkpolicy -n observability
```

### SSL Connection Errors

```bash
# Verify SSL certificate
openssl s_client -connect kafka.company.com:9093 -showcerts

# Check SASL credentials
kubectl get secret -n observability kg-rca-kafka-secret -o yaml
```

## Uninstall

```bash
helm uninstall kg-rca-agent --namespace observability

# Optional: Remove namespace
kubectl delete namespace observability
```

## Resource Usage

Typical resource consumption per node:

| Component | CPU (avg) | Memory (avg) | Notes |
|-----------|-----------|--------------|-------|
| Vector | 50-100m | 128-256Mi | Per node (DaemonSet) |
| Event Exporter | 10-50m | 64-128Mi | Single replica |
| State Watcher | 50-100m | 128-256Mi | Single replica |

**Total per cluster**: ~200-500m CPU, ~400-800Mi memory

## Support

- Documentation: https://docs.lumniverse.com/kg-rca
- Issues: https://github.com/lumniverse/kg-rca-agent/issues
- Email: support@lumniverse.com

## License

Proprietary - Contact support@lumniverse.com for licensing
