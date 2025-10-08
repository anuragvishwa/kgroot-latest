# Production Deployment Guide - Knowledge Graph RCA System

## 🎯 Overview

This guide covers deploying the complete Knowledge Graph RCA System to a client's Kubernetes cluster using Helm.

**Single-Command Deployment**: Install the entire system with one Helm command.

---

## 📦 What Gets Deployed

### Core Components
1. **Neo4j** - Knowledge graph database (production-tuned)
2. **Kafka + Zookeeper** - Message streaming
3. **Graph Builder** - Kafka → Neo4j processor with RCA engine
4. **KG API** - REST API for RCA queries
5. **Embedding Service** - Vector search (sentence-transformers)

### K8s Monitoring Components
6. **State Watcher** - Tracks K8s resource changes
7. **Vector** - Log collection and normalization
8. **K8s Event Exporter** - Exports K8s events
9. **Alerts Enricher** - Enriches Prometheus alerts

### Observability Stack
10. **Prometheus** - Metrics collection
11. **Grafana** - Dashboards
12. **Kafka UI** - Kafka monitoring (optional)
13. **Alertmanager** - Alert routing (optional)

### Automation
14. **Cleanup CronJob** - Automated data retention

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites
- Kubernetes cluster (v1.24+)
- Helm 3.x installed
- kubectl configured
- At least 16GB RAM available
- 100GB storage

### Single-Command Installation

```bash
# Add Helm repository (when published)
helm repo add kg-rca https://charts.kg-rca.com
helm repo update

# Install with default values
helm install kg-rca kg-rca/kg-rca-system \
  --namespace observability \
  --create-namespace \
  --wait

# Or install from local chart
cd production/helm-chart
helm install kg-rca ./kg-rca-system \
  --namespace observability \
  --create-namespace \
  --wait
```

**That's it!** The system is now deployed and running.

---

## 📋 Detailed Installation

### Step 1: Prepare Configuration

Create a `values-production.yaml` file:

```yaml
# Production configuration
global:
  namespace: observability
  imageRegistry: your-registry.com  # Your container registry

# Neo4j - High Availability (optional)
neo4j:
  auth:
    password: <CHANGE-THIS-STRONG-PASSWORD>
  resources:
    requests:
      cpu: 2000m
      memory: 8Gi
    limits:
      cpu: 4000m
      memory: 12Gi
  persistence:
    enabled: true
    storageClass: fast-ssd  # Your storage class
    size: 50Gi

# Kafka - Production tuning
kafka:
  replicaCount: 3
  config:
    numPartitions: 6
    replicationFactor: 3
  resources:
    requests:
      cpu: 1000m
      memory: 4Gi
  persistence:
    enabled: true
    size: 50Gi

# Graph Builder - Auto-scaling
graphBuilder:
  image:
    repository: your-registry.com/graph-builder
    tag: v1.0.0
  replicaCount: 2
  resources:
    requests:
      cpu: 1000m
      memory: 2Gi
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70

# KG API - Public endpoint
kgApi:
  image:
    repository: your-registry.com/kg-api
    tag: v1.0.0
  replicaCount: 3
  ingress:
    enabled: true
    className: nginx
    hosts:
      - host: kg-api.your-domain.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: kg-api-tls
        hosts:
          - kg-api.your-domain.com

# Embedding Service
embeddingService:
  image:
    repository: your-registry.com/embedding-service
    tag: v1.0.0
  replicaCount: 2
  resources:
    requests:
      cpu: 1000m
      memory: 2Gi

# Prometheus
prometheus:
  persistence:
    enabled: true
    size: 100Gi
  retention: 30d

# Grafana - Public dashboard
grafana:
  service:
    type: LoadBalancer
  ingress:
    enabled: true
    hosts:
      - host: grafana.your-domain.com

# Security
security:
  tls:
    enabled: true
    neo4j:
      secretName: neo4j-tls
    kafka:
      secretName: kafka-tls
```

### Step 2: Create Secrets

```bash
# Create namespace
kubectl create namespace observability

# Create Neo4j credentials
kubectl create secret generic neo4j-creds \
  --from-literal=password=$(openssl rand -base64 32) \
  -n observability

# Create TLS certificates (if needed)
kubectl create secret tls kg-api-tls \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  -n observability

kubectl create secret tls neo4j-tls \
  --cert=path/to/neo4j.crt \
  --key=path/to/neo4j.key \
  -n observability
```

### Step 3: Install with Custom Values

```bash
helm install kg-rca ./kg-rca-system \
  --namespace observability \
  --values values-production.yaml \
  --wait \
  --timeout 15m
```

### Step 4: Verify Installation

```bash
# Check all pods are running
kubectl get pods -n observability

# Expected output:
# NAME                                  READY   STATUS    RESTARTS   AGE
# kg-rca-neo4j-0                       1/1     Running   0          5m
# kg-rca-kafka-0                       1/1     Running   0          5m
# kg-rca-zookeeper-0                   1/1     Running   0          5m
# kg-rca-graph-builder-xxx             1/1     Running   0          5m
# kg-rca-kg-api-xxx                    1/1     Running   0          5m
# kg-rca-embedding-service-xxx         1/1     Running   0          5m
# kg-rca-state-watcher-xxx             1/1     Running   0          5m
# kg-rca-vector-xxx                    1/1     Running   0          5m
# kg-rca-event-exporter-xxx            1/1     Running   0          5m
# kg-rca-prometheus-xxx                1/1     Running   0          5m
# kg-rca-grafana-xxx                   1/1     Running   0          5m

# Check services
kubectl get svc -n observability

# Test API endpoint
kubectl port-forward svc/kg-rca-kg-api 8080:8080 -n observability
curl http://localhost:8080/healthz
```

---

## 🔧 Configuration Options

### Minimal Configuration (Small Clusters)

```yaml
# values-minimal.yaml
neo4j:
  resources:
    requests:
      cpu: 500m
      memory: 2Gi
  persistence:
    size: 20Gi

kafka:
  replicaCount: 1
  resources:
    requests:
      cpu: 500m
      memory: 2Gi

graphBuilder:
  replicaCount: 1

prometheus:
  enabled: false  # Use existing Prometheus

grafana:
  enabled: false  # Use existing Grafana
```

Install:
```bash
helm install kg-rca ./kg-rca-system \
  --namespace observability \
  --values values-minimal.yaml
```

---

### High Availability Configuration

```yaml
# values-ha.yaml
neo4j:
  replicaCount: 3  # Cluster mode
  resources:
    requests:
      cpu: 4000m
      memory: 16Gi

kafka:
  replicaCount: 3
  config:
    replicationFactor: 3

graphBuilder:
  replicaCount: 3
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 20

kgApi:
  replicaCount: 5

embeddingService:
  replicaCount: 3
```

---

### Air-Gapped Installation

For environments without internet access:

```bash
# 1. Download all images
images=(
  "neo4j:5.20"
  "bitnami/kafka:3.7"
  "bitnami/zookeeper:3.9"
  "your-registry/graph-builder:v1.0.0"
  "your-registry/kg-api:v1.0.0"
  "your-registry/embedding-service:v1.0.0"
  "your-registry/state-watcher:latest"
  "timberio/vector:0.35.0-alpine"
  "opsgenie/kubernetes-event-exporter:1.7"
  "prom/prometheus:latest"
  "grafana/grafana:latest"
)

for image in "${images[@]}"; do
  docker pull $image
  docker save $image -o $(echo $image | tr '/:' '_').tar
done

# 2. Transfer tars to air-gapped environment

# 3. Load images
for tar in *.tar; do
  docker load -i $tar
done

# 4. Push to private registry
for image in "${images[@]}"; do
  docker tag $image private-registry.local/$image
  docker push private-registry.local/$image
done

# 5. Install with private registry
helm install kg-rca ./kg-rca-system \
  --set global.imageRegistry=private-registry.local \
  --namespace observability
```

---

## 📊 Post-Installation Steps

### 1. Access Dashboards

```bash
# Grafana
kubectl port-forward svc/kg-rca-grafana 3000:3000 -n observability
# Open: http://localhost:3000 (admin/admin)

# Neo4j Browser
kubectl port-forward svc/kg-rca-neo4j 7474:7474 -n observability
# Open: http://localhost:7474

# Kafka UI
kubectl port-forward svc/kg-rca-kafka-ui 8080:8080 -n observability
# Open: http://localhost:8080

# KG API
kubectl port-forward svc/kg-rca-kg-api 8080:8080 -n observability
# Test: curl http://localhost:8080/api/v1/stats
```

### 2. Test Vector Search

```bash
# Test semantic search
curl -X POST http://localhost:8080/api/v1/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what caused the memory leak",
    "top_k": 5
  }' | jq .
```

### 3. Test RCA Query

```bash
# Get graph statistics
curl http://localhost:8080/api/v1/stats | jq .

# Perform RCA (replace with real event_id)
curl -X POST http://localhost:8080/api/v1/rca \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "your-event-id",
    "min_confidence": 0.6
  }' | jq .
```

### 4. Configure Grafana Dashboards

```bash
# Import dashboards
kubectl apply -f production/helm-chart/kg-rca-system/dashboards/
```

---

## 🔄 Upgrading

```bash
# Upgrade to new version
helm upgrade kg-rca ./kg-rca-system \
  --namespace observability \
  --values values-production.yaml

# Rollback if needed
helm rollback kg-rca -n observability
```

---

## 🗑️ Uninstalling

```bash
# Uninstall chart (keeps PVCs)
helm uninstall kg-rca -n observability

# Delete PVCs (WARNING: deletes all data)
kubectl delete pvc -l app.kubernetes.io/instance=kg-rca -n observability

# Delete namespace
kubectl delete namespace observability
```

---

## 🔍 Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl get pods -n observability

# Check logs
kubectl logs -f deployment/kg-rca-graph-builder -n observability

# Describe pod for events
kubectl describe pod kg-rca-graph-builder-xxx -n observability
```

### Neo4j Connection Issues

```bash
# Test Neo4j connectivity
kubectl exec -it kg-rca-graph-builder-xxx -n observability -- \
  sh -c 'echo "RETURN 1" | cypher-shell -u neo4j -p $NEO4J_PASS'
```

### Kafka Consumer Lag

```bash
# Check consumer lag
kubectl exec -it kg-rca-kafka-0 -n observability -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group kg-builder
```

### Embedding Service Not Responding

```bash
# Check embedding service health
kubectl port-forward svc/kg-rca-embedding-service 5000:5000 -n observability
curl http://localhost:5000/healthz
```

---

## 📈 Monitoring & Alerts

### Set Up Prometheus Alerts

```yaml
# Create AlertmanagerConfig
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-alerts
  namespace: observability
data:
  alerts.yml: |
    groups:
      - name: kg-rca-alerts
        interval: 30s
        rules:
          - alert: HighConsumerLag
            expr: kg_kafka_consumer_lag > 1000
            for: 5m
            annotations:
              summary: "High Kafka consumer lag"
              description: "Consumer lag is {{ $value }}"

          - alert: Neo4jConnectionErrors
            expr: rate(kg_neo4j_connection_errors_total[5m]) > 1
            for: 2m
            annotations:
              summary: "Neo4j connection errors detected"

          - alert: HighErrorRate
            expr: rate(kg_messages_processed_total{status="error"}[5m]) > 10
            for: 5m
            annotations:
              summary: "High message processing error rate"
```

---

## 🔐 Security Best Practices

### 1. Use Kubernetes Secrets

```bash
# Create secret for Neo4j password
kubectl create secret generic neo4j-creds \
  --from-literal=password=$(openssl rand -base64 32) \
  -n observability

# Update values.yaml
neo4j:
  auth:
    existingSecret: neo4j-creds
    existingSecretPasswordKey: password
```

### 2. Enable Network Policies

```yaml
security:
  networkPolicy:
    enabled: true
```

### 3. Enable TLS

```yaml
security:
  tls:
    enabled: true
    neo4j:
      secretName: neo4j-tls
    kafka:
      secretName: kafka-tls
```

### 4. Enable Pod Security Policies

```yaml
security:
  podSecurityPolicy:
    enabled: true
```

---

## 📊 Performance Tuning

### For High-Volume Environments (>10k events/min)

```yaml
kafka:
  config:
    numPartitions: 12
    compressionType: lz4

graphBuilder:
  replicaCount: 5
  resources:
    requests:
      cpu: 2000m
      memory: 4Gi
  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 20

neo4j:
  config:
    heapSize: 8G
    pageCacheSize: 4G
```

---

## 💡 Tips & Best Practices

1. **Start with minimal config**, scale up as needed
2. **Monitor Prometheus dashboards** for first 24 hours
3. **Set up alerts** for consumer lag, errors, circuit breaker
4. **Test backup/restore** before going live
5. **Document custom configurations** in your values file
6. **Use separate storage classes** for different components
7. **Enable autoscaling** for graph-builder in production
8. **Schedule cleanup jobs** during low-traffic hours
9. **Keep retention policy** aligned with compliance requirements
10. **Test disaster recovery** procedure

---

## 📞 Support

- **Documentation**: See `production/prod-docs/`
- **API Reference**: See `production/api-docs/API_REFERENCE.md`
- **Query Examples**: See `production/neo4j-queries/QUERY_LIBRARY.md`
- **Vector Search**: See `production/vector-search/`

---

## 🎓 Next Steps

After successful installation:

1. ✅ Access Grafana dashboards
2. ✅ Test semantic search queries
3. ✅ Perform sample RCA analysis
4. ✅ Set up monitoring alerts
5. ✅ Configure backup schedule
6. ✅ Train team on RCA queries
7. ✅ Integrate with existing tools (Slack, PagerDuty, etc.)
8. ✅ Document custom use cases
9. ✅ Set up CI/CD for updates
10. ✅ Perform load testing

---

**Your production-ready Knowledge Graph RCA System is now deployed!** 🚀
