# Server Deployment Guide

**Version**: 1.0.0
**Last Updated**: 2025-01-09
**Estimated Time**: 30-45 minutes

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Installation Steps](#installation-steps)
4. [Configuration](#configuration)
5. [Post-Deployment Verification](#post-deployment-verification)
6. [DNS Configuration](#dns-configuration)
7. [SSL/TLS Setup](#ssltls-setup)
8. [Monitoring Setup](#monitoring-setup)
9. [Backup Configuration](#backup-configuration)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Infrastructure Requirements

| Resource | Minimum | Recommended | Production |
|----------|---------|-------------|------------|
| **Kubernetes Cluster** | 1.24+ | 1.28+ | 1.28+ |
| **Nodes** | 3 | 5 | 10+ |
| **Total CPU** | 20 cores | 50 cores | 100+ cores |
| **Total Memory** | 64 GB | 128 GB | 400+ GB |
| **Storage** | 500 GB SSD | 2 TB SSD | 3+ TB NVMe |
| **Network** | 1 Gbps | 10 Gbps | 25 Gbps |

### Software Requirements

```bash
# Required tools
kubectl >= 1.24
helm >= 3.10
git >= 2.30

# Optional but recommended
kubectx/kubens
k9s (Kubernetes CLI manager)
jq (JSON processor)
yq (YAML processor)
```

### Cloud Provider Setup

**AWS**:
```bash
# EKS cluster
eksctl create cluster \
  --name kg-rca-server \
  --region us-east-1 \
  --nodegroup-name standard-workers \
  --node-type m5.4xlarge \
  --nodes 5 \
  --nodes-min 3 \
  --nodes-max 10 \
  --managed

# Storage class (gp3 SSD)
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
  iops: "16000"
  throughput: "1000"
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
EOF
```

**GCP**:
```bash
# GKE cluster
gcloud container clusters create kg-rca-server \
  --region us-central1 \
  --machine-type n2-standard-16 \
  --num-nodes 5 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 10 \
  --disk-type pd-ssd \
  --disk-size 500

# Storage class (pd-ssd)
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/gce-pd
parameters:
  type: pd-ssd
reclaimPolicy: Retain
EOF
```

**Azure**:
```bash
# AKS cluster
az aks create \
  --resource-group kg-rca \
  --name kg-rca-server \
  --location eastus \
  --node-count 5 \
  --node-vm-size Standard_D16s_v3 \
  --enable-cluster-autoscaler \
  --min-count 3 \
  --max-count 10

# Storage class (Premium SSD)
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/azure-disk
parameters:
  storageaccounttype: Premium_LRS
  kind: Managed
reclaimPolicy: Retain
EOF
```

### Domain Requirements

You'll need:
- **API Domain**: `api.kg-rca.yourcompany.com`
- **Grafana Domain**: `grafana.kg-rca.yourcompany.com`
- **Kafka Domain**: `kafka.kg-rca.yourcompany.com` (optional, can use IP)

### External Services

**Stripe Account** (for billing):
```bash
# Get API keys from Stripe Dashboard
STRIPE_PUBLISHABLE_KEY="pk_live_..."
STRIPE_SECRET_KEY="sk_live_..."
STRIPE_WEBHOOK_SECRET="whsec_..."
```

---

## Pre-Deployment Checklist

```bash
# 1. Verify cluster access
kubectl cluster-info
kubectl get nodes

# Expected output:
# NAME                STATUS   ROLE    AGE   VERSION
# node-1              Ready    node    10m   v1.28.0
# node-2              Ready    node    10m   v1.28.0
# node-3              Ready    node    10m   v1.28.0

# 2. Verify Helm is installed
helm version

# Expected output:
# version.BuildInfo{Version:"v3.13.0", ...}

# 3. Check available storage classes
kubectl get storageclass

# Expected output:
# NAME        PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE
# fast-ssd    kubernetes.io/aws-ebs   Retain          WaitForFirstConsumer
# standard    kubernetes.io/aws-ebs   Delete          Immediate

# 4. Verify sufficient resources
kubectl top nodes

# Expected output (example):
# NAME     CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
# node-1   2000m        12%    8Gi             25%
# node-2   1800m        11%    7Gi             21%
# node-3   2200m        13%    9Gi             28%

# 5. Test internet connectivity
kubectl run test-pod --image=curlimages/curl --rm -it --restart=Never -- \
  curl -s https://www.google.com

# Expected: HTML output
```

---

## Installation Steps

### Step 1: Clone Repository

```bash
# Clone the KG RCA repository
git clone https://github.com/your-org/kg-rca-platform.git
cd kg-rca-platform/saas/server/helm-chart/kg-rca-server
```

### Step 2: Create Production Values File

```bash
# Copy default values
cp values.yaml production-values.yaml

# Edit production-values.yaml
nano production-values.yaml
```

**Minimum Required Changes**:

```yaml
# production-values.yaml

global:
  domain: kg-rca.yourcompany.com  # CHANGE THIS
  environment: production

# Neo4j - Database
neo4j:
  auth:
    password: "YOUR_SECURE_PASSWORD_HERE"  # CHANGE THIS

  resources:
    requests:
      cpu: 8000m
      memory: 32Gi
    limits:
      cpu: 16000m
      memory: 64Gi

  persistence:
    storageClassName: "fast-ssd"  # Match your storage class
    size: 500Gi

# Kafka - Event Stream
kafka:
  resources:
    requests:
      cpu: 4000m
      memory: 8Gi
    limits:
      cpu: 8000m
      memory: 16Gi

  persistence:
    storageClassName: "fast-ssd"
    size: 1Ti

  service:
    type: LoadBalancer  # Or NodePort if LoadBalancer not available

# Graph Builder - RCA Engine
graphBuilder:
  replicaCount: 5

  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 50

# KG API - REST API
kgApi:
  replicaCount: 10

  ingress:
    enabled: true
    className: nginx
    hosts:
      - host: api.kg-rca.yourcompany.com  # CHANGE THIS
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: kg-api-tls
        hosts:
          - api.kg-rca.yourcompany.com  # CHANGE THIS

# PostgreSQL - Billing Database
postgresql:
  auth:
    password: "YOUR_SECURE_PASSWORD_HERE"  # CHANGE THIS

# Grafana - Monitoring
grafana:
  adminPassword: "YOUR_SECURE_PASSWORD_HERE"  # CHANGE THIS

  ingress:
    enabled: true
    hosts:
      - host: grafana.kg-rca.yourcompany.com  # CHANGE THIS
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: grafana-tls
        hosts:
          - grafana.kg-rca.yourcompany.com  # CHANGE THIS

# Backup configuration
backup:
  enabled: true
  storage:
    type: s3  # or gcs, azure
    bucket: "kg-rca-backups-yourcompany"  # CHANGE THIS
    region: "us-east-1"  # CHANGE THIS

# Secrets (pass via --set or external secret manager)
secrets:
  neo4j:
    password: ""  # Set via --set or sealed secrets
  stripe:
    apiKey: ""    # Set via --set or sealed secrets
  postgresql:
    password: ""  # Set via --set or sealed secrets
```

### Step 3: Install Prerequisites

#### Install Ingress Controller

```bash
# Install nginx-ingress
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

helm install nginx-ingress ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.service.type=LoadBalancer \
  --set controller.metrics.enabled=true

# Wait for external IP
kubectl get svc -n ingress-nginx -w

# Expected output:
# NAME                    TYPE           EXTERNAL-IP      PORT(S)
# nginx-ingress-controller LoadBalancer  52.12.34.56     80:30080/TCP,443:30443/TCP
```

#### Install Cert-Manager (for TLS)

```bash
# Install cert-manager
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true

# Create Let's Encrypt issuer
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@yourcompany.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### Step 4: Install KG RCA Server

```bash
# Install the Helm chart
helm install kg-rca-server . \
  --namespace kg-rca-server \
  --create-namespace \
  --values production-values.yaml \
  --set secrets.neo4j.password="YOUR_NEO4J_PASSWORD" \
  --set secrets.postgresql.password="YOUR_POSTGRES_PASSWORD" \
  --set secrets.stripe.apiKey="YOUR_STRIPE_SECRET_KEY" \
  --timeout 20m \
  --wait

# Expected output:
# NAME: kg-rca-server
# LAST DEPLOYED: Thu Jan 9 10:00:00 2025
# NAMESPACE: kg-rca-server
# STATUS: deployed
# REVISION: 1
# NOTES:
# Thank you for installing kg-rca-server!
#
# Your release is named kg-rca-server.
# ...
```

**Installation Progress**:

```bash
# Watch pod creation
kubectl get pods -n kg-rca-server -w

# Expected sequence:
# 1. Zookeeper pods start (zookeeper-0, zookeeper-1, zookeeper-2)
# 2. Kafka pods start (kafka-0, kafka-1, kafka-2, kafka-3, kafka-4)
# 3. Neo4j pods start (neo4j-0, neo4j-1, neo4j-2)
# 4. PostgreSQL pod starts (postgresql-0)
# 5. Graph Builder pods start (graph-builder-xxxxx)
# 6. KG API pods start (kg-api-xxxxx)
# 7. Monitoring pods start (prometheus, grafana)
```

### Step 5: Wait for All Pods to be Ready

```bash
# Check pod status
kubectl get pods -n kg-rca-server

# Expected output (all Running, all READY):
# NAME                              READY   STATUS    RESTARTS   AGE
# zookeeper-0                       1/1     Running   0          5m
# zookeeper-1                       1/1     Running   0          4m
# zookeeper-2                       1/1     Running   0          3m
# kafka-0                           1/1     Running   0          4m
# kafka-1                           1/1     Running   0          3m
# kafka-2                           1/1     Running   0          2m
# kafka-3                           1/1     Running   0          1m
# kafka-4                           1/1     Running   0          1m
# neo4j-0                           1/1     Running   0          3m
# neo4j-1                           1/1     Running   0          2m
# neo4j-2                           1/1     Running   0          1m
# postgresql-0                      1/1     Running   0          3m
# graph-builder-6b8d9f7c8-xxxxx    1/1     Running   0          2m
# graph-builder-6b8d9f7c8-yyyyy    1/1     Running   0          2m
# graph-builder-6b8d9f7c8-zzzzz    1/1     Running   0          2m
# kg-api-7d9c8b6a5-xxxxx           1/1     Running   0          1m
# kg-api-7d9c8b6a5-yyyyy           1/1     Running   0          1m
# prometheus-0                      1/1     Running   0          2m
# grafana-7f8c6d5b4-xxxxx          1/1     Running   0          1m
```

**Troubleshooting Pod Issues**:

```bash
# If pods are not starting, check logs
kubectl logs <pod-name> -n kg-rca-server

# Check events
kubectl get events -n kg-rca-server --sort-by='.lastTimestamp'

# Describe pod for more details
kubectl describe pod <pod-name> -n kg-rca-server
```

---

## Configuration

### Neo4j Configuration

```bash
# Access Neo4j Browser (port-forward for initial setup)
kubectl port-forward -n kg-rca-server svc/neo4j 7474:7474 7687:7687

# Open browser: http://localhost:7474
# Login: neo4j / YOUR_NEO4J_PASSWORD

# Verify cluster status
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_PASSWORD \
  "CALL dbms.cluster.overview() YIELD role, addresses RETURN role, addresses;"

# Expected output:
# role       | addresses
# -----------|------------------
# LEADER     | neo4j-0:7687
# FOLLOWER   | neo4j-1:7687
# FOLLOWER   | neo4j-2:7687

# Create system database (if not exists)
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_PASSWORD \
  "CREATE DATABASE system IF NOT EXISTS;"
```

### Kafka Configuration

```bash
# Verify Kafka cluster
kubectl exec -n kg-rca-server kafka-0 -- kafka-broker-api-versions.sh \
  --bootstrap-server kafka:9092

# Expected output:
# kafka-0:9092 (id: 0 rack: null) -> (
#   Produce(0): 0 to 9 [usable: 9],
#   Fetch(1): 0 to 13 [usable: 13],
#   ...
# )

# List topics (should be empty initially)
kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --list

# Create test topic
kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --create \
  --topic test-topic \
  --partitions 6 \
  --replication-factor 3

# Verify replication
kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --topic test-topic

# Expected output:
# Topic: test-topic       PartitionCount: 6       ReplicationFactor: 3
# Topic: test-topic       Partition: 0    Leader: 1       Replicas: 1,2,3 Isr: 1,2,3
# ...
```

### PostgreSQL Configuration

```bash
# Access PostgreSQL
kubectl exec -n kg-rca-server postgresql-0 -it -- psql -U billing

# Create tables for billing
CREATE TABLE IF NOT EXISTS clients (
  id VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  plan VARCHAR(50) NOT NULL DEFAULT 'free',
  status VARCHAR(50) NOT NULL DEFAULT 'active',
  stripe_customer_id VARCHAR(255),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
  id BIGSERIAL PRIMARY KEY,
  client_id VARCHAR(255) NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  key_hash VARCHAR(255) NOT NULL UNIQUE,
  key_prefix VARCHAR(20) NOT NULL,
  permissions JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMP,
  INDEX idx_key_hash (key_hash),
  INDEX idx_client_id (client_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id BIGSERIAL PRIMARY KEY,
  client_id VARCHAR(255) NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
  plan VARCHAR(50) NOT NULL,
  status VARCHAR(50) NOT NULL,
  current_period_start TIMESTAMP NOT NULL,
  current_period_end TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  INDEX idx_client_id (client_id)
);

CREATE TABLE IF NOT EXISTS usage_metrics (
  id BIGSERIAL PRIMARY KEY,
  client_id VARCHAR(255) NOT NULL,
  metric VARCHAR(100) NOT NULL,
  value BIGINT NOT NULL,
  timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
  INDEX idx_client_metric_time (client_id, metric, timestamp)
);

# Verify tables
\dt

# Expected output:
#            List of relations
#  Schema |      Name       | Type  | Owner
# --------+-----------------+-------+--------
#  public | clients         | table | billing
#  public | api_keys        | table | billing
#  public | subscriptions   | table | billing
#  public | usage_metrics   | table | billing
```

---

## Post-Deployment Verification

### Health Checks

```bash
# 1. Check all pods are running
kubectl get pods -n kg-rca-server

# 2. Check all services
kubectl get svc -n kg-rca-server

# Expected output:
# NAME           TYPE           CLUSTER-IP       EXTERNAL-IP     PORT(S)
# neo4j          ClusterIP      10.100.10.10     <none>          7474/TCP,7687/TCP
# kafka          LoadBalancer   10.100.10.20     52.12.34.78     9092:30092/TCP
# graph-builder  ClusterIP      10.100.10.30     <none>          9090/TCP
# kg-api         ClusterIP      10.100.10.40     <none>          8080/TCP
# postgresql     ClusterIP      10.100.10.50     <none>          5432/TCP
# prometheus     ClusterIP      10.100.10.60     <none>          9090/TCP
# grafana        ClusterIP      10.100.10.70     <none>          3000/TCP

# 3. Check ingress
kubectl get ingress -n kg-rca-server

# Expected output:
# NAME      CLASS   HOSTS                           ADDRESS         PORTS
# kg-api    nginx   api.kg-rca.yourcompany.com     52.12.34.56     80,443
# grafana   nginx   grafana.kg-rca.yourcompany.com 52.12.34.56     80,443

# 4. Test API health endpoint
kubectl port-forward -n kg-rca-server svc/kg-api 8080:8080 &
curl http://localhost:8080/healthz

# Expected output:
# ok

# 5. Test Graph Builder metrics endpoint
kubectl port-forward -n kg-rca-server svc/graph-builder 9090:9090 &
curl http://localhost:9090/metrics

# Expected output (sample):
# kg_messages_processed_total{topic="test",status="success"} 0
# kg_rca_links_created_total 0
# ...
```

### Component Verification

**Neo4j Cluster Health**:

```bash
# Check cluster status
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_PASSWORD \
  "CALL dbms.cluster.overview() YIELD role, databases RETURN role, databases;"

# Expected: 1 LEADER, 2 FOLLOWERS

# Test write operation
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_PASSWORD \
  "CREATE DATABASE test_db;"

# List databases
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_PASSWORD \
  "SHOW DATABASES;"

# Expected output:
# name     | type   | status
# ---------|--------|--------
# system   | system | online
# test_db  | user   | online
```

**Kafka Cluster Health**:

```bash
# Test producer
kubectl exec -n kg-rca-server kafka-0 -it -- bash -c \
  'echo "test message" | kafka-console-producer.sh \
    --bootstrap-server kafka:9092 \
    --topic test-topic'

# Test consumer
kubectl exec -n kg-rca-server kafka-0 -it -- kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic test-topic \
  --from-beginning \
  --max-messages 1

# Expected output:
# test message
```

**Prometheus Metrics**:

```bash
# Port-forward Prometheus
kubectl port-forward -n kg-rca-server svc/prometheus 9090:9090 &

# Query Prometheus API
curl 'http://localhost:9090/api/v1/query?query=up'

# Expected output:
# {
#   "status": "success",
#   "data": {
#     "resultType": "vector",
#     "result": [
#       {"metric": {"__name__": "up", "job": "graph-builder"}, "value": [1704796800, "1"]},
#       {"metric": {"__name__": "up", "job": "kg-api"}, "value": [1704796800, "1"]},
#       ...
#     ]
#   }
# }
```

**Grafana Access**:

```bash
# Port-forward Grafana
kubectl port-forward -n kg-rca-server svc/grafana 3000:3000 &

# Open browser: http://localhost:3000
# Login: admin / YOUR_GRAFANA_PASSWORD

# Import dashboards (manual step in Grafana UI):
# 1. Go to Dashboards → Import
# 2. Import dashboard ID: 15489 (Kubernetes Cluster Monitoring)
# 3. Import dashboard ID: 7589 (Kafka Overview)
```

---

## DNS Configuration

### Update DNS Records

```bash
# Get LoadBalancer IPs
INGRESS_IP=$(kubectl get svc -n ingress-nginx nginx-ingress-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

KAFKA_IP=$(kubectl get svc -n kg-rca-server kafka \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo "Ingress IP: $INGRESS_IP"
echo "Kafka IP: $KAFKA_IP"
```

**Add DNS A Records**:

```
api.kg-rca.yourcompany.com      → $INGRESS_IP
grafana.kg-rca.yourcompany.com  → $INGRESS_IP
kafka.kg-rca.yourcompany.com    → $KAFKA_IP
```

**Verify DNS Propagation**:

```bash
# Wait for DNS to propagate (can take 5-60 minutes)
dig api.kg-rca.yourcompany.com +short

# Expected output: $INGRESS_IP

# Test HTTPS access
curl https://api.kg-rca.yourcompany.com/healthz

# Expected output:
# ok
```

---

## SSL/TLS Setup

### Verify Cert-Manager

```bash
# Check cert-manager pods
kubectl get pods -n cert-manager

# Expected output:
# NAME                          READY   STATUS    RESTARTS   AGE
# cert-manager-xxxxx            1/1     Running   0          10m
# cert-manager-cainjector-xxxxx 1/1     Running   0          10m
# cert-manager-webhook-xxxxx    1/1     Running   0          10m

# Check ClusterIssuer
kubectl get clusterissuer

# Expected output:
# NAME               READY   AGE
# letsencrypt-prod   True    10m
```

### Verify Certificates

```bash
# Check certificates
kubectl get certificate -n kg-rca-server

# Expected output:
# NAME           READY   SECRET         AGE
# kg-api-tls     True    kg-api-tls     5m
# grafana-tls    True    grafana-tls    5m

# Check certificate details
kubectl describe certificate kg-api-tls -n kg-rca-server

# Expected:
# Status:
#   Conditions:
#     Type:    Ready
#     Status:  True
#   Not After: 2025-04-09T10:00:00Z
```

### Test TLS

```bash
# Test TLS handshake
openssl s_client -connect api.kg-rca.yourcompany.com:443 -servername api.kg-rca.yourcompany.com

# Expected:
# Verify return code: 0 (ok)

# Test HTTPS
curl -v https://api.kg-rca.yourcompany.com/healthz

# Expected:
# * SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
# < HTTP/2 200
# ok
```

---

## Monitoring Setup

### Access Grafana

```bash
# Get Grafana admin password (if not set)
kubectl get secret -n kg-rca-server grafana -o jsonpath='{.data.admin-password}' | base64 -d

# Access Grafana
# URL: https://grafana.kg-rca.yourcompany.com
# User: admin
# Password: <from above or your custom password>
```

### Configure Dashboards

**Import Pre-built Dashboards**:

1. **Server Overview Dashboard**:
   - Import JSON from: `saas/server/grafana-dashboards/server-overview.json`

2. **RCA Quality Dashboard**:
   - Import JSON from: `saas/server/grafana-dashboards/rca-quality.json`

3. **Performance Dashboard**:
   - Import JSON from: `saas/server/grafana-dashboards/performance.json`

**Create AlertManager Config**:

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: alertmanager-config
  namespace: kg-rca-server
data:
  alertmanager.yml: |
    global:
      resolve_timeout: 5m
      slack_api_url: 'YOUR_SLACK_WEBHOOK_URL'

    route:
      receiver: 'slack-notifications'
      group_by: ['alertname', 'cluster']
      group_wait: 10s
      group_interval: 10s
      repeat_interval: 12h

    receivers:
    - name: 'slack-notifications'
      slack_configs:
      - channel: '#kg-rca-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'
EOF

# Restart AlertManager
kubectl rollout restart deployment alertmanager -n kg-rca-server
```

---

## Backup Configuration

### Configure S3 Backup Storage

```bash
# Create S3 bucket
aws s3 mb s3://kg-rca-backups-yourcompany --region us-east-1

# Create IAM policy
cat > backup-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::kg-rca-backups-yourcompany",
        "arn:aws:s3:::kg-rca-backups-yourcompany/*"
      ]
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name KGRCABackupPolicy \
  --policy-document file://backup-policy.json

# Create service account with IRSA (EKS) or workload identity (GKE)
# Follow cloud provider documentation for attaching IAM role to service account
```

### Test Backup

```bash
# Trigger manual backup (Neo4j)
kubectl exec -n kg-rca-server neo4j-0 -- neo4j-admin backup \
  --backup-dir=/backups \
  --database=system

# Verify backup files
kubectl exec -n kg-rca-server neo4j-0 -- ls -lh /backups

# Expected output:
# total 100M
# -rw-r--r-- 1 neo4j neo4j 100M Jan  9 10:30 system.backup
```

---

## Troubleshooting

### Common Issues

#### Issue 1: Pods Stuck in Pending

```bash
# Check pod events
kubectl describe pod <pod-name> -n kg-rca-server

# Common causes:
# - Insufficient resources: Increase node pool size
# - Storage class not found: Verify storage class exists
# - PVC not bound: Check PVC status with kubectl get pvc

# Solution: Scale node pool
# AWS EKS:
eksctl scale nodegroup --cluster=kg-rca-server --name=standard-workers --nodes=7

# GKE:
gcloud container clusters resize kg-rca-server --num-nodes=7
```

#### Issue 2: Neo4j Cluster Not Forming

```bash
# Check Neo4j logs
kubectl logs -n kg-rca-server neo4j-0 --tail=100

# Common issues:
# - Clock skew between nodes
# - Network policies blocking communication
# - Insufficient memory

# Solution: Check cluster status
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p PASSWORD \
  "CALL dbms.cluster.overview();"

# If cluster is stuck, restart pods one by one
kubectl delete pod neo4j-0 -n kg-rca-server
# Wait for neo4j-0 to be ready
kubectl delete pod neo4j-1 -n kg-rca-server
# Wait for neo4j-1 to be ready
kubectl delete pod neo4j-2 -n kg-rca-server
```

#### Issue 3: Kafka Brokers Not Ready

```bash
# Check Kafka logs
kubectl logs -n kg-rca-server kafka-0 --tail=100

# Common issues:
# - Zookeeper not ready
# - Disk space full
# - Memory issues

# Solution: Verify Zookeeper
kubectl exec -n kg-rca-server zookeeper-0 -- zkServer.sh status

# Expected output:
# Mode: follower (or leader)

# Check disk space
kubectl exec -n kg-rca-server kafka-0 -- df -h /kafka

# If disk full, increase PVC size:
kubectl patch pvc kafka-data-kafka-0 -n kg-rca-server \
  -p '{"spec":{"resources":{"requests":{"storage":"2Ti"}}}}'
```

#### Issue 4: Ingress Not Working

```bash
# Check ingress controller
kubectl get pods -n ingress-nginx

# Check ingress resource
kubectl get ingress -n kg-rca-server kg-api -o yaml

# Common issues:
# - DNS not pointing to LoadBalancer IP
# - Certificate not issued
# - Firewall blocking port 443

# Solution: Check certificate
kubectl describe certificate kg-api-tls -n kg-rca-server

# If certificate failed, check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager

# Manually trigger certificate
kubectl delete certificate kg-api-tls -n kg-rca-server
# Wait for automatic recreation by ingress
```

#### Issue 5: High Memory Usage

```bash
# Check pod resource usage
kubectl top pods -n kg-rca-server

# If Neo4j is using too much memory, adjust heap size
kubectl edit statefulset neo4j -n kg-rca-server
# Modify: server.memory.heap.max_size

# If Kafka is using too much memory, adjust Java heap
kubectl edit statefulset kafka -n kg-rca-server
# Modify: KAFKA_HEAP_OPTS
```

### Getting Help

```bash
# Collect diagnostic information
kubectl get all -n kg-rca-server > diagnostics.txt
kubectl get events -n kg-rca-server --sort-by='.lastTimestamp' >> diagnostics.txt
kubectl top nodes >> diagnostics.txt
kubectl top pods -n kg-rca-server >> diagnostics.txt

# Get logs from all pods
for pod in $(kubectl get pods -n kg-rca-server -o name); do
  echo "=== $pod ===" >> logs.txt
  kubectl logs -n kg-rca-server $pod --tail=500 >> logs.txt
done

# Share diagnostics.txt and logs.txt with support
```

---

## Next Steps

After successful deployment:

1. **Configure DNS** - Point your domains to the LoadBalancer IPs
2. **Set up monitoring** - Configure alerts and dashboards
3. **Test the system** - Run validation scripts
4. **Onboard first client** - Follow [Client Onboarding Guide](02-CLIENT-ONBOARDING.md)
5. **Set up billing** - Configure Stripe webhook
6. **Enable backups** - Test restore procedure

---

## Deployment Checklist

- [ ] Kubernetes cluster created and accessible
- [ ] Storage classes configured
- [ ] Ingress controller installed
- [ ] Cert-manager installed
- [ ] Production values file created
- [ ] Secrets configured (Neo4j, PostgreSQL, Stripe)
- [ ] Helm chart installed
- [ ] All pods running and healthy
- [ ] Neo4j cluster formed (1 leader, 2 followers)
- [ ] Kafka cluster healthy (5 brokers)
- [ ] PostgreSQL tables created
- [ ] DNS records created
- [ ] TLS certificates issued
- [ ] Grafana accessible
- [ ] Monitoring dashboards imported
- [ ] Backup configuration tested
- [ ] Health checks passing

---

**Deployment Complete!**

Your KG RCA server is now ready to onboard clients.

**Next**: [Client Onboarding Guide](02-CLIENT-ONBOARDING.md)

---

**Document Version**: 1.0.0
**Maintained By**: Platform Engineering Team
**Last Review**: 2025-01-09
