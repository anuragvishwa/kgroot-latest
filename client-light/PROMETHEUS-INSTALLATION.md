# Prometheus Installation Guide

The KG RCA Agent Helm chart can optionally install `kube-prometheus-stack` if Prometheus is not already available in your cluster.

## Automatic Prometheus Installation

### Enable Prometheus Installation

To automatically install Prometheus during the Helm chart installation, set `prometheus.install=true`:

```bash
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  --set client.id="your-client-id" \
  --set client.kafka.brokers="kafka-broker:9092" \
  --set prometheus.install=true
```

### What Gets Installed

When `prometheus.install=true`, the chart will:

1. Check if Prometheus already exists in the specified namespace (default: `monitoring`)
2. If not found, install `kube-prometheus-stack` with the following components:
   - **Prometheus Server** - Metrics collection and storage
   - **AlertManager** - Alert management and routing
   - **kube-state-metrics** - Kubernetes cluster metrics
   - **Grafana** (optional, disabled by default)

### Configuration Options

You can customize the Prometheus installation using the following values:

```yaml
prometheus:
  # Enable automatic installation
  install: true

  # Namespace where Prometheus will be installed
  namespace: "monitoring"

  # Release name for the Prometheus installation
  releaseName: "kube-prometheus-stack"

  # Prometheus configuration
  config:
    grafana:
      enabled: false  # Set to true to install Grafana

    prometheus:
      enabled: true
      service:
        port: 9090
      prometheusSpec:
        resources:
          requests:
            cpu: 200m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 2Gi
        retention: 7d

    alertmanager:
      enabled: true
      service:
        port: 9093

    kubeStateMetrics:
      enabled: true

    nodeExporter:
      enabled: false  # Set to true for node-level metrics
```

### Using a Custom Values File

Create a `values.yaml` file:

```yaml
client:
  id: "your-client-id"
  kafka:
    brokers: "kafka-broker:9092"

prometheus:
  install: true
  namespace: "monitoring"
  config:
    grafana:
      enabled: true  # Enable Grafana dashboard
    nodeExporter:
      enabled: true  # Enable node metrics
```

Install with the custom values:

```bash
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  -f values.yaml
```

## Using Existing Prometheus

If you already have Prometheus installed in your cluster, you can skip the automatic installation and just configure the connection:

```bash
helm install kg-rca-agent kg-rca-agent/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  --set client.id="your-client-id" \
  --set client.kafka.brokers="kafka-broker:9092" \
  --set prometheus.install=false \
  --set stateWatcher.prometheusUrl="http://your-prometheus-service.monitoring.svc:9090"
```

## Manual Installation (Alternative)

If you prefer to install Prometheus manually, you can use the provided script:

```bash
cd client-light/scripts
./check-or-install-prometheus.sh
```

This script will:
1. Check if Prometheus is already installed
2. Install `kube-prometheus-stack` if not found
3. Display the Prometheus URL to use in your configuration

## Verification

After installation, verify that Prometheus is running:

```bash
# Check Prometheus pods
kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus

# Check Prometheus service
kubectl get svc -n monitoring -l app.kubernetes.io/name=prometheus

# Check AlertManager
kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager
```

## Accessing Prometheus UI

To access the Prometheus UI:

```bash
# Port-forward Prometheus
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090

# Access at: http://localhost:9090
```

To access AlertManager UI:

```bash
# Port-forward AlertManager
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093

# Access at: http://localhost:9093
```

## Troubleshooting

### Check Installation Status

```bash
# Check Helm release
helm status kube-prometheus-stack -n monitoring

# Check installation job logs
kubectl logs -n observability -l component=prometheus-installer
```

### Prometheus Not Starting

If Prometheus pods are not starting, check:

```bash
# Check pod status
kubectl describe pod -n monitoring <prometheus-pod-name>

# Check for resource constraints
kubectl top nodes
```

### Update Prometheus Configuration

To update the Prometheus configuration after installation:

```bash
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set <your-configuration-changes>
```

## Uninstalling Prometheus

If you need to uninstall Prometheus:

```bash
# Uninstall the Prometheus Helm release
helm uninstall kube-prometheus-stack -n monitoring

# (Optional) Delete the namespace
kubectl delete namespace monitoring
```

## Production Considerations

For production deployments:

1. **Storage**: Configure persistent storage for Prometheus data:
   ```yaml
   prometheus:
     config:
       prometheus:
         prometheusSpec:
           storageSpec:
             volumeClaimTemplate:
               spec:
                 storageClassName: "your-storage-class"
                 accessModes: ["ReadWriteOnce"]
                 resources:
                   requests:
                     storage: 50Gi
   ```

2. **Retention**: Adjust retention period based on your needs:
   ```yaml
   prometheus:
     config:
       prometheus:
         prometheusSpec:
           retention: 30d  # Keep metrics for 30 days
   ```

3. **Resources**: Adjust resource limits for your cluster size:
   ```yaml
   prometheus:
     config:
       prometheus:
         prometheusSpec:
           resources:
             requests:
               cpu: 500m
               memory: 2Gi
             limits:
               cpu: 2000m
               memory: 4Gi
   ```

4. **High Availability**: Enable HA mode for production:
   ```yaml
   prometheus:
     config:
       prometheus:
         prometheusSpec:
           replicas: 2
   ```

## Support

For issues related to:
- KG RCA Agent: [GitHub Issues](https://github.com/anuragvishwa/kgroot-latest/issues)
- kube-prometheus-stack: [Prometheus Community Charts](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)