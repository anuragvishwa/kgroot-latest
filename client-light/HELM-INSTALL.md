# Direct Helm Installation

Install KG RCA Agent directly from GitHub release without cloning the repo.

> **Note:** All Docker images are hosted on Docker Hub and publicly available. No image building or registry authentication required!

## Method 1: Install from GitHub Release (Recommended)

```bash
# 1. Download Helm chart package
wget https://github.com/anuragvishwa/kgroot-latest/releases/download/v1.0.2/kg-rca-agent-1.0.1.tgz

# 2. Create your values file
cat > my-values.yaml <<EOF
client:
  id: "my-cluster-prod"
  kafka:
    brokers: "98.90.147.12:9092"
EOF

# 3. Install
helm install kg-rca-agent kg-rca-agent-1.0.1.tgz \
  --values my-values.yaml \
  --namespace observability \
  --create-namespace

# 4. Verify
kubectl get pods -n observability
```

## Method 2: Install from Git Repository

```bash
# 1. Clone repo
git clone https://github.com/anuragvishwa/kgroot-latest.git
cd kgroot-latest/client-light

# 2. Create values
cat > my-values.yaml <<EOF
client:
  id: "my-cluster"
  kafka:
    brokers: "98.90.147.12:9092"
EOF

# 3. Install
helm install kg-rca-agent ./helm-chart \
  --values my-values.yaml \
  --namespace observability \
  --create-namespace
```

## Configuration Examples

### Minimal (Testing)
```yaml
client:
  id: "test-cluster"
  kafka:
    brokers: "98.90.147.12:9092"
```

### Production with SSL
```yaml
client:
  id: "prod-us-west"
  apiKey: "your-api-key"
  kafka:
    brokers: "kafka.lumniverse.com:9093"
    sasl:
      enabled: true
      mechanism: SCRAM-SHA-512
      username: "prod-us-west"
      password: "secure-password"
```

### With Namespace Filtering
```yaml
client:
  id: "prod-cluster"
  kafka:
    brokers: "98.90.147.12:9092"
  monitoredNamespaces:
    - production
    - staging
```

## Prometheus & Alerts Integration

1. **Point the state watcher at your Prometheus service.**
   ```yaml
   stateWatcher:
     prometheusUrl: "http://<prom-service>.<namespace>.svc:9090"
   ```
   Discover the in-cluster URL with:
   ```bash
   kubectl get svc -n monitoring -l app.kubernetes.io/name=prometheus \
     -o jsonpath='{.items[0].metadata.name}'
   ```

2. **Send Alertmanager webhooks to the client chart.**  
   The Helm release exposes a ClusterIP service named like `kg-rca-agent-<release>-alert-webhook` (Vector http_server). Confirm the port with:
   ```bash
   kubectl get svc -n observability -l component=alert-webhook
   ```
   Add the resulting URL to your Alertmanager configuration so Prometheus alerts reach Kafka and the alerts enricher. Use:
   `http://<service>.<namespace>.svc:9090/alerts`

3. **Know when Kafka topics populate.**

   | Topic | Source | When to expect messages |
   |-------|--------|-------------------------|
   | `logs.normalized` | Vector DaemonSet | Always (pod logs) |
   | `events.normalized` | Kubernetes Event Exporter | Always (cluster events) |
   | `state.k8s.*` | State Watcher | Always (resource/topology state) |
   | `state.prom.targets` | State Watcher | After `stateWatcher.prometheusUrl` resolves |
   | `alerts.enriched` | Alerts enricher | After Alertmanager webhooks are routed |
   | `raw.*`, `alerts.normalized`, `dlq.*` | Legacy/optional processors | Stay empty with the light client |

## Upgrade

```bash
# Download new version
wget https://github.com/anuragvishwa/kgroot-latest/releases/download/v1.0.3/kg-rca-agent-1.0.3.tgz

# Upgrade
helm upgrade kg-rca-agent kg-rca-agent-1.0.3.tgz \
  --values my-values.yaml \
  --namespace observability
```

## Uninstall

```bash
helm uninstall kg-rca-agent --namespace observability
kubectl delete namespace observability
```

## Troubleshooting

### Download Failed
If wget fails, download manually from:
https://github.com/anuragvishwa/kgroot-latest/releases/tag/v1.0.2

### Image Pull Errors
If you see `ImagePullBackOff` errors, the images are being pulled from Docker Hub:
- `anuragvishwa/kg-alert-receiver:1.0.2`
- `anuragvishwa/kg-state-watcher:1.0.2`
- `opsgenie/kubernetes-event-exporter:v1.4`
- `timberio/vector:0.34.0-alpine`

Check your cluster's internet connectivity and Docker Hub access.

See [DOCKER-HUB.md](DOCKER-HUB.md) for more details on images.

### Installation Failed
```bash
# Check Helm syntax
helm lint kg-rca-agent-1.0.1.tgz

# Dry run first
helm install kg-rca-agent kg-rca-agent-1.0.1.tgz \
  --values my-values.yaml \
  --namespace observability \
  --dry-run --debug
```

## Next Steps

After installation, verify data is reaching the server:
- See [INSTALL-TEST-GUIDE.md](INSTALL-TEST-GUIDE.md) for verification steps
