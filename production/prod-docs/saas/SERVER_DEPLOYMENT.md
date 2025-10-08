# Server Deployment Guide - YOUR Infrastructure

## 🎯 Overview

This guide covers deploying YOUR central SaaS infrastructure that will serve multiple clients.

**What you're deploying**:
- Neo4j (multi-tenant knowledge graph)
- Kafka (multi-tenant message broker)
- Graph Builder (RCA engine)
- KG API (REST endpoints)
- Billing system
- Monitoring stack

---

## 📋 Prerequisites

### Infrastructure Requirements

| Component | CPU | Memory | Storage | Count |
|-----------|-----|--------|---------|-------|
| Neo4j | 8 cores | 32GB | 500GB SSD | 3 nodes |
| Kafka | 4 cores | 16GB | 1TB SSD | 5 nodes |
| Graph Builder | 2 cores | 4GB | - | 5-50 pods |
| KG API | 1 core | 2GB | - | 10 pods |
| PostgreSQL | 2 cores | 8GB | 100GB | 3 nodes |
| Redis | 1 core | 4GB | 50GB | 3 nodes |

**Total minimum**: 100 CPU cores, 400GB RAM, 3TB storage

### Kubernetes Cluster
- Kubernetes v1.24+
- Helm 3.x
- kubectl configured
- Storage class with SSD (for Neo4j, Kafka)
- LoadBalancer support (or Ingress controller)

### External Services
- Domain name (e.g., kg-rca.your-company.com)
- SSL certificates (Let's Encrypt or purchased)
- Email service (for notifications)
- Payment processor (Stripe, etc.)

---

## 🚀 Deployment Steps

### Step 1: Prepare Configuration

Create `production-values.yaml`:

```yaml
global:
  domain: kg-rca.your-company.com
  imageRegistry: your-registry.com

# Neo4j - Multi-tenant
neo4j:
  auth:
    password: $(openssl rand -base64 32)
  resources:
    requests:
      cpu: 8000m
      memory: 32Gi
  persistence:
    storageClass: fast-ssd
    size: 500Gi
  replicaCount: 3

# Kafka - Multi-tenant
kafka:
  replicaCount: 5
  resources:
    requests:
      cpu: 4000m
      memory: 16Gi
  persistence:
    size: 1Ti
  config:
    numPartitions: 12
    replicationFactor: 3

# Graph Builder - Auto-scaling
graphBuilder:
  image:
    repository: your-registry.com/graph-builder
    tag: v1.0.0
  replicaCount: 5
  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 50

# KG API - Public facing
kgApi:
  image:
    repository: your-registry.com/kg-api
    tag: v1.0.0
  replicaCount: 10
  ingress:
    enabled: true
    hosts:
      - host: api.kg-rca.your-company.com
    tls:
      - secretName: api-tls
        hosts:
          - api.kg-rca.your-company.com

# Billing
billing:
  enabled: true
  database:
    host: postgres.billing.svc.cluster.local

# Monitoring
prometheus:
  enabled: true
  retention: 90d

grafana:
  enabled: true
  adminPassword: $(openssl rand -base64 32)
  ingress:
    enabled: true
    hosts:
      - grafana.kg-rca.your-company.com
```

---

### Step 2: Create Secrets

```bash
# Create namespace
kubectl create namespace kg-rca-server

# Neo4j password
kubectl create secret generic neo4j-creds \
  --from-literal=password=$(openssl rand -base64 32) \
  -n kg-rca-server

# Kafka encryption keys
kubectl create secret generic kafka-creds \
  --from-file=server.keystore.jks \
  --from-file=server.truststore.jks \
  -n kg-rca-server

# SSL certificates
kubectl create secret tls api-tls \
  --cert=api.crt \
  --key=api.key \
  -n kg-rca-server

# Database passwords
kubectl create secret generic postgres-creds \
  --from-literal=password=$(openssl rand -base64 32) \
  -n kg-rca-server

# Stripe API key (for billing)
kubectl create secret generic stripe-creds \
  --from-literal=api-key=sk_live_... \
  -n kg-rca-server
```

---

### Step 3: Deploy Infrastructure

```bash
cd production/helm-chart/server

# Install
helm install kg-rca-server ./kg-rca-server \
  --namespace kg-rca-server \
  --values production-values.yaml \
  --wait \
  --timeout 30m
```

---

### Step 4: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n kg-rca-server

# Expected output:
# NAME                                  READY   STATUS    RESTARTS   AGE
# neo4j-0                               1/1     Running   0          10m
# neo4j-1                               1/1     Running   0          10m
# neo4j-2                               1/1     Running   0          10m
# kafka-0                               1/1     Running   0          10m
# kafka-1                               1/1     Running   0          10m
# kafka-2                               1/1     Running   0          10m
# kafka-3                               1/1     Running   0          10m
# kafka-4                               1/1     Running   0          10m
# graph-builder-xxx                     1/1     Running   0          10m
# kg-api-xxx                            1/1     Running   0          10m
# billing-service-xxx                   1/1     Running   0          10m
# prometheus-xxx                        1/1     Running   0          10m
# grafana-xxx                           1/1     Running   0          10m

# Check services
kubectl get svc -n kg-rca-server

# Get external endpoints
kubectl get ingress -n kg-rca-server
```

---

### Step 5: Configure DNS

```bash
# Get LoadBalancer IPs
INGRESS_IP=$(kubectl get ingress kg-api -n kg-rca-server -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Add DNS records
api.kg-rca.your-company.com      A  ${INGRESS_IP}
kafka.kg-rca.your-company.com    A  ${INGRESS_IP}
grafana.kg-rca.your-company.com  A  ${INGRESS_IP}
```

---

### Step 6: Initialize Database

```bash
# Connect to PostgreSQL
kubectl exec -it postgres-0 -n kg-rca-server -- psql -U postgres

-- Create tables
CREATE TABLE clients (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(50) REFERENCES clients(id),
    key_hash VARCHAR(255) NOT NULL,
    permissions JSON,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(50) REFERENCES clients(id),
    plan VARCHAR(50) NOT NULL,
    price_monthly DECIMAL(10,2),
    billing_cycle VARCHAR(20),
    next_billing_date DATE,
    status VARCHAR(20) DEFAULT 'active'
);

CREATE TABLE usage_metrics (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(50) REFERENCES clients(id),
    metric VARCHAR(50) NOT NULL,
    value BIGINT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    INDEX idx_client_metric_time (client_id, metric, timestamp)
);

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(50) REFERENCES clients(id),
    amount DECIMAL(10,2) NOT NULL,
    period_start DATE,
    period_end DATE,
    status VARCHAR(20) DEFAULT 'pending',
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### Step 7: Test Installation

```bash
# Test API health
curl https://api.kg-rca.your-company.com/healthz

# Test Neo4j connection
kubectl exec -it neo4j-0 -n kg-rca-server -- \
  cypher-shell -u neo4j -p $(kubectl get secret neo4j-creds -n kg-rca-server -o jsonpath='{.data.password}' | base64 -d) \
  "RETURN 1"

# Test Kafka
kubectl exec -it kafka-0 -n kg-rca-server -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list

# Access Grafana
open https://grafana.kg-rca.your-company.com
```

---

## 🔧 Post-Deployment Configuration

### 1. Set Up Monitoring

```bash
# Import Grafana dashboards
kubectl apply -f production/helm-chart/server/dashboards/

# Configure alerts
kubectl apply -f production/helm-chart/server/alerts/
```

### 2. Configure Backup

```bash
# Neo4j backup
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: neo4j-backup
  namespace: kg-rca-server
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: neo4j:5.20
            command:
            - /bin/bash
            - -c
            - |
              neo4j-admin database dump neo4j --to-path=/backup/neo4j-\$(date +%Y%m%d).dump
              aws s3 cp /backup/neo4j-\$(date +%Y%m%d).dump s3://your-backup-bucket/
          restartPolicy: OnFailure
EOF
```

### 3. Set Up Rate Limiting

Kong API Gateway is configured automatically. Verify:

```bash
# Check rate limits
curl -H "X-API-Key: test-key" \
  https://api.kg-rca.your-company.com/api/v1/stats

# Headers show rate limit info:
# X-RateLimit-Limit: 1000
# X-RateLimit-Remaining: 999
# X-RateLimit-Reset: 1234567890
```

---

## 👥 Client Onboarding

### Automated Onboarding API

```bash
# Create admin API endpoint
curl -X POST https://api.kg-rca.your-company.com/admin/clients \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "email": "admin@acme.com",
    "plan": "pro"
  }'

# Response:
{
  "client_id": "client-acme-abc123",
  "api_key": "acme_xyz789_secret",
  "kafka_credentials": {
    "username": "client-acme-abc123",
    "password": "kafka_pass_xyz"
  },
  "install_command": "helm install kg-rca-agent kg-rca/kg-rca-agent --set client.id=client-acme-abc123 --set client.apiKey=acme_xyz789_secret"
}
```

### Manual Onboarding

```bash
# 1. Create Neo4j database for client
kubectl exec -it neo4j-0 -n kg-rca-server -- \
  cypher-shell -u neo4j -p $(kubectl get secret neo4j-creds -n kg-rca-server -o jsonpath='{.data.password}' | base64 -d) \
  "CREATE DATABASE client_acme_abc123_kg"

# 2. Create Kafka user and ACLs
kubectl exec -it kafka-0 -n kg-rca-server -- \
  kafka-configs.sh --bootstrap-server localhost:9092 \
    --alter --add-config 'SCRAM-SHA-512=[password=kafka_pass_xyz]' \
    --entity-type users --entity-name client-acme-abc123

kubectl exec -it kafka-0 -n kg-rca-server -- \
  kafka-acls.sh --bootstrap-server localhost:9092 \
    --add --allow-principal User:client-acme-abc123 \
    --operation Write --topic "client-acme-abc123.*"

# 3. Add to database
kubectl exec -it postgres-0 -n kg-rca-server -- psql -U postgres -c "
INSERT INTO clients (id, name, email, plan)
VALUES ('client-acme-abc123', 'Acme Corp', 'admin@acme.com', 'pro');

INSERT INTO api_keys (client_id, key_hash, permissions)
VALUES ('client-acme-abc123', 'hash_of_api_key', '{\"rca\": true, \"search\": true}');
"

# 4. Send client installation package
cat > acme-install.yaml <<EOF
client:
  id: "client-acme-abc123"
  apiKey: "acme_xyz789_secret"
  serverUrl: "https://api.kg-rca.your-company.com"
  kafka:
    brokers: "kafka.kg-rca.your-company.com:9092"
    sasl:
      username: "client-acme-abc123"
      password: "kafka_pass_xyz"
EOF
```

---

## 📊 Monitoring YOUR Platform

### Key Dashboards

**System Overview**:
- Total clients active
- Events/second across all clients
- Neo4j cluster health
- Kafka cluster health

**Per-Client Metrics**:
- Events ingested (last 24h)
- RCA queries (last 24h)
- Storage used (GB)
- API calls (last 24h)

**Billing Metrics**:
- MRR (Monthly Recurring Revenue)
- Overage charges
- Churn rate
- Average revenue per client

### Critical Alerts

```yaml
- alert: Neo4jClusterDown
  expr: up{job="neo4j"} < 2
  for: 5m
  annotations:
    summary: "Neo4j cluster degraded"

- alert: KafkaHighLag
  expr: kafka_consumergroup_lag > 100000
  for: 10m
  annotations:
    summary: "Kafka consumer lag >100k"

- alert: ClientOverPlan
  expr: client_events_today / client_plan_limit > 1.2
  annotations:
    summary: "Client {{ $labels.client_id }} over plan by 20%"
```

---

## 🔒 Security Hardening

### 1. Enable TLS Everywhere

```bash
# Update Neo4j for TLS
kubectl patch statefulset neo4j -n kg-rca-server -p '
spec:
  template:
    spec:
      containers:
      - name: neo4j
        env:
        - name: NEO4J_dbms_ssl_policy_bolt_enabled
          value: "true"
'

# Update Kafka for TLS
kubectl patch statefulset kafka -n kg-rca-server -p '
spec:
  template:
    spec:
      containers:
      - name: kafka
        env:
        - name: KAFKA_CFG_SSL_KEYSTORE_LOCATION
          value: "/opt/kafka/config/certs/kafka.keystore.jks"
'
```

### 2. Network Policies

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kg-api-policy
  namespace: kg-rca-server
spec:
  podSelector:
    matchLabels:
      app: kg-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: neo4j
    ports:
    - protocol: TCP
      port: 7687
EOF
```

---

## 💰 Billing Setup

### Stripe Integration

```bash
# Set Stripe webhook
curl -X POST https://api.stripe.com/v1/webhook_endpoints \
  -u sk_live_...: \
  -d url="https://api.kg-rca.your-company.com/webhooks/stripe" \
  -d "enabled_events[]"="invoice.payment_succeeded" \
  -d "enabled_events[]"="invoice.payment_failed"
```

### Usage Tracking

Graph Builder automatically tracks usage to PostgreSQL:

```sql
-- Query usage for billing
SELECT
    client_id,
    metric,
    SUM(value) as total,
    DATE(timestamp) as date
FROM usage_metrics
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY client_id, metric, DATE(timestamp);
```

---

## 🚨 Troubleshooting

### Neo4j Issues

```bash
# Check cluster status
kubectl exec -it neo4j-0 -n kg-rca-server -- \
  cypher-shell -u neo4j -p password \
  "CALL dbms.cluster.overview()"

# Check logs
kubectl logs -f neo4j-0 -n kg-rca-server
```

### Kafka Issues

```bash
# Check broker status
kubectl exec -it kafka-0 -n kg-rca-server -- \
  kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# Check consumer lag
kubectl exec -it kafka-0 -n kg-rca-server -- \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --describe --all-groups
```

### API Issues

```bash
# Check API logs
kubectl logs -f deployment/kg-api -n kg-rca-server

# Test API endpoint
curl -v https://api.kg-rca.your-company.com/healthz
```

---

## 📈 Scaling

### Horizontal Scaling

```bash
# Scale Graph Builder
kubectl scale deployment graph-builder \
  --replicas=20 \
  -n kg-rca-server

# Scale KG API
kubectl scale deployment kg-api \
  --replicas=30 \
  -n kg-rca-server
```

### Vertical Scaling

```bash
# Increase Neo4j resources
kubectl patch statefulset neo4j -n kg-rca-server -p '
spec:
  template:
    spec:
      containers:
      - name: neo4j
        resources:
          requests:
            cpu: 16000m
            memory: 64Gi
'
```

---

## 🎓 Next Steps

1. ✅ Server deployed and verified
2. ✅ Monitoring configured
3. ✅ Backup scheduled
4. ⏭️ **Onboard first client**: See `CLIENT_ONBOARDING.md`
5. ⏭️ **Set up billing**: Configure Stripe
6. ⏭️ **Launch**: Announce to customers!

---

**Your SaaS platform is ready!** 🚀
