# Client Onboarding Guide

**Version**: 1.0.0
**Last Updated**: 2025-01-09
**Estimated Time**: 20-30 minutes

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Server-Side Setup](#server-side-setup)
4. [Client-Side Installation](#client-side-installation)
5. [Verification](#verification)
6. [Testing Data Flow](#testing-data-flow)
7. [Troubleshooting](#troubleshooting)
8. [Client Offboarding](#client-offboarding)

---

## Overview

This guide covers the complete process of onboarding a new client to the KG RCA SaaS platform.

### Onboarding Flow

```
┌─────────────────────────────────────────────────────────┐
│ STEP 1: Server-Side Setup (Service Provider)           │
│ ------------------------------------------------         │
│ 1. Create client record in PostgreSQL                  │
│ 2. Generate API key                                     │
│ 3. Create Kafka SASL credentials                       │
│ 4. Create Neo4j database                                │
│ 5. Configure Kafka ACLs                                 │
│ 6. Generate client installation package                │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ↓ Send credentials to client
                  │
┌─────────────────┴───────────────────────────────────────┐
│ STEP 2: Client-Side Installation (Customer)            │
│ ------------------------------------------------         │
│ 1. Receive installation package                        │
│ 2. Create Kubernetes namespace                          │
│ 3. Install Helm chart with credentials                 │
│ 4. Verify agent pods running                            │
│ 5. Verify data flow to server                          │
└─────────────────────────────────────────────────────────┘
```

### Roles

- **Service Provider (You)**: Runs the server infrastructure
- **Client (Customer)**: Deploys agents in their Kubernetes cluster

---

## Prerequisites

### Server-Side Requirements

- Server infrastructure deployed and healthy
- PostgreSQL accessible
- Neo4j cluster running
- Kafka cluster running
- Admin access to server namespace

### Client-Side Requirements

- Kubernetes cluster (version 1.20+)
- `kubectl` access to cluster
- Helm 3.10+ installed
- Outbound internet access (HTTPS + Kafka)
- Minimum resources: 2 CPU, 4 GB RAM

---

## Server-Side Setup

### Step 1: Create Client Record

```bash
# Connect to PostgreSQL
kubectl exec -n kg-rca-server postgresql-0 -it -- psql -U billing

# Insert client record
INSERT INTO clients (id, name, email, plan, status, created_at, updated_at)
VALUES (
  'client-acme-abc123',
  'Acme Corporation',
  'admin@acme.com',
  'pro',
  'active',
  NOW(),
  NOW()
);

# Verify insertion
SELECT * FROM clients WHERE id = 'client-acme-abc123';

# Expected output:
#       id          |      name        |      email       | plan | status
# ------------------+------------------+------------------+------+--------
# client-acme-abc123| Acme Corporation | admin@acme.com   | pro  | active
```

### Step 2: Generate API Key

```bash
# Generate API key (using script or manually)
cat > generate-api-key.sh <<'EOF'
#!/bin/bash

CLIENT_ID=$1
if [ -z "$CLIENT_ID" ]; then
  echo "Usage: $0 <client-id>"
  exit 1
fi

# Generate random 32-character suffix
RANDOM_SUFFIX=$(openssl rand -hex 16)

# Format: kg_{client_id}_{random_32_chars}
API_KEY="kg_${CLIENT_ID}_${RANDOM_SUFFIX}"

# Hash for storage (SHA-256)
API_KEY_HASH=$(echo -n "$API_KEY" | sha256sum | awk '{print $1}')

# Prefix for display
API_KEY_PREFIX=$(echo "$API_KEY" | cut -c1-20)

echo "API Key: $API_KEY"
echo "API Key Hash: $API_KEY_HASH"
echo "API Key Prefix: $API_KEY_PREFIX"

# Store in database
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing <<SQL
INSERT INTO api_keys (client_id, key_hash, key_prefix, created_at)
VALUES ('$CLIENT_ID', '$API_KEY_HASH', '$API_KEY_PREFIX', NOW());
SQL

echo "API key created and stored successfully"
EOF

chmod +x generate-api-key.sh

# Generate API key for client
./generate-api-key.sh client-acme-abc123

# Expected output:
# API Key: kg_client-acme-abc123_9f4b2e8d1c7a6f3e5b8d2c1a9f4b2e8d
# API Key Hash: a1b2c3d4e5f6...
# API Key Prefix: kg_client-acme-abc1...
# API key created and stored successfully

# IMPORTANT: Save the full API key securely - it won't be shown again!
API_KEY="kg_client-acme-abc123_9f4b2e8d1c7a6f3e5b8d2c1a9f4b2e8d"
```

### Step 3: Create Kafka SASL Credentials

```bash
# Generate Kafka password
KAFKA_PASSWORD=$(openssl rand -base64 32)

echo "Kafka Username: client-acme-abc123"
echo "Kafka Password: $KAFKA_PASSWORD"

# Create SASL credentials in Kafka
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --add-config "SCRAM-SHA-512=[password=$KAFKA_PASSWORD]" \
  --entity-type users \
  --entity-name client-acme-abc123

# Expected output:
# Completed updating config for user client-acme-abc123

# Verify
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --entity-type users \
  --entity-name client-acme-abc123

# Expected output:
# SCRAM-SHA-512=salt=...
```

### Step 4: Create Neo4j Database

```bash
# Create database for client
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_NEO4J_PASSWORD \
  "CREATE DATABASE client_acme_abc123_kg IF NOT EXISTS;"

# Wait for database to be online
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_NEO4J_PASSWORD \
  "SHOW DATABASES WHERE name = 'client_acme_abc123_kg';"

# Expected output:
# name                      | type | status
# --------------------------|------|-------
# client_acme_abc123_kg     | user | online

# Initialize schema
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_NEO4J_PASSWORD \
  -d client_acme_abc123_kg \
  "CREATE INDEX resource_name IF NOT EXISTS FOR (r:Resource) ON (r.name);
   CREATE INDEX episodic_timestamp IF NOT EXISTS FOR (e:Episodic) ON (e.timestamp);
   CREATE INDEX incident_timestamp IF NOT EXISTS FOR (i:Incident) ON (i.timestamp);"

# Verify indexes
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p YOUR_NEO4J_PASSWORD \
  -d client_acme_abc123_kg \
  "SHOW INDEXES;"

# Expected output:
# name                    | state  | type
# ------------------------|--------|------
# resource_name           | ONLINE | BTREE
# episodic_timestamp      | ONLINE | BTREE
# incident_timestamp      | ONLINE | BTREE
```

### Step 5: Configure Kafka ACLs

```bash
# Allow client to write to their topics
kubectl exec -n kg-rca-server kafka-0 -- kafka-acls.sh \
  --bootstrap-server kafka:9092 \
  --add \
  --allow-principal User:client-acme-abc123 \
  --operation Write \
  --operation Describe \
  --topic "client-acme-abc123.*" \
  --resource-pattern-type prefixed

# Expected output:
# Adding ACLs for resource 'Topic:PREFIXED:client-acme-abc123.*':
#   (principal=User:client-acme-abc123, host=*, operation=WRITE, permissionType=ALLOW)
#   (principal=User:client-acme-abc123, host=*, operation=DESCRIBE, permissionType=ALLOW)

# Verify ACLs
kubectl exec -n kg-rca-server kafka-0 -- kafka-acls.sh \
  --bootstrap-server kafka:9092 \
  --list \
  --principal User:client-acme-abc123

# Expected output:
# Current ACLs for principal User:client-acme-abc123:
#   ResourceType: Topic, PatternType: PREFIXED, Name: client-acme-abc123.*, Operations: WRITE, DESCRIBE
```

### Step 6: Create Kafka Topics

```bash
# Create topics for client
TOPICS=(
  "client-acme-abc123.events.normalized"
  "client-acme-abc123.logs.normalized"
  "client-acme-abc123.state.k8s.resource"
  "client-acme-abc123.state.k8s.topology"
  "client-acme-abc123.alerts.raw"
)

for TOPIC in "${TOPICS[@]}"; do
  kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
    --bootstrap-server kafka:9092 \
    --create \
    --topic "$TOPIC" \
    --partitions 6 \
    --replication-factor 3 \
    --if-not-exists

  echo "Created topic: $TOPIC"
done

# Verify topics
kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --list | grep "client-acme-abc123"

# Expected output:
# client-acme-abc123.alerts.raw
# client-acme-abc123.events.normalized
# client-acme-abc123.logs.normalized
# client-acme-abc123.state.k8s.resource
# client-acme-abc123.state.k8s.topology
```

### Step 7: Generate Installation Package

```bash
# Get Kafka LoadBalancer IP/hostname
KAFKA_BROKER=$(kubectl get svc -n kg-rca-server kafka \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# If IP is empty, try hostname
if [ -z "$KAFKA_BROKER" ]; then
  KAFKA_BROKER=$(kubectl get svc -n kg-rca-server kafka \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
fi

echo "Kafka Broker: $KAFKA_BROKER:9092"

# Create client installation values file
cat > acme-client-values.yaml <<EOF
# KG RCA Agent Configuration for Acme Corporation
# Generated: $(date)
# Client ID: client-acme-abc123

client:
  # Client identification
  id: "client-acme-abc123"

  # API key for authentication
  apiKey: "$API_KEY"

  # Server connection
  serverUrl: "https://api.kg-rca.yourcompany.com"

  # Kafka connection
  kafka:
    brokers: "$KAFKA_BROKER:9092"
    sasl:
      enabled: true
      mechanism: SCRAM-SHA-512
      username: "client-acme-abc123"
      password: "$KAFKA_PASSWORD"

# State Watcher - Kubernetes resource monitoring
stateWatcher:
  enabled: true
  replicaCount: 1

# Vector - Log collection
vector:
  enabled: true

# Event Exporter - Kubernetes events
eventExporter:
  enabled: true

# Alert Receiver - Prometheus alerts
alertReceiver:
  enabled: true

# RBAC
rbac:
  create: true

serviceAccount:
  create: true
EOF

echo "Installation package created: acme-client-values.yaml"

# Create README for client
cat > acme-client-README.md <<EOF
# KG RCA Agent Installation - Acme Corporation

## Quick Start

1. Install Helm chart:
   \`\`\`bash
   helm repo add kg-rca https://charts.kg-rca.yourcompany.com
   helm repo update

   helm install kg-rca-agent kg-rca/kg-rca-agent \\
     --namespace kg-rca \\
     --create-namespace \\
     --values acme-client-values.yaml
   \`\`\`

2. Verify installation:
   \`\`\`bash
   kubectl get pods -n kg-rca
   \`\`\`

3. Test connectivity:
   \`\`\`bash
   kubectl logs -n kg-rca deployment/kg-rca-state-watcher
   \`\`\`

## Support

- Email: support@yourcompany.com
- Slack: #kg-rca-support
- Documentation: https://docs.kg-rca.yourcompany.com

## Credentials

- Client ID: client-acme-abc123
- API Key: [Stored in acme-client-values.yaml]
- Kafka Credentials: [Stored in acme-client-values.yaml]

**Important**: Keep these credentials secure and do not share them.
EOF

echo "Client README created: acme-client-README.md"

# Create installation package
tar czf acme-client-installation.tar.gz \
  acme-client-values.yaml \
  acme-client-README.md

echo "Installation package: acme-client-installation.tar.gz"

# Send to client securely
# - Email with encrypted attachment
# - Secure file share (Dropbox, Google Drive)
# - Customer portal download
```

### Step 8: Notify Client

```bash
# Send email to client with installation package
# Template:

cat > client-welcome-email.txt <<EOF
Subject: Welcome to KG RCA Platform - Installation Package

Dear Acme Corporation,

Thank you for subscribing to the KG RCA Platform!

Your account is now ready. Please find attached your installation package containing:
- Helm values file (acme-client-values.yaml)
- Installation instructions (acme-client-README.md)

Your account details:
- Client ID: client-acme-abc123
- Plan: Pro
- Monthly Events: Up to 1M events/day
- RCA Queries: Up to 1K queries/hour

Getting Started:
1. Extract the installation package
2. Follow the instructions in acme-client-README.md
3. Deploy the agent Helm chart in your Kubernetes cluster
4. Verify connectivity using the included test commands

Support:
- Documentation: https://docs.kg-rca.yourcompany.com
- Email: support@yourcompany.com
- Slack: #kg-rca-support

Dashboard:
- Access your dashboard at: https://api.kg-rca.yourcompany.com/dashboard
- Login with your API key

We're here to help! Don't hesitate to reach out if you have any questions.

Best regards,
The KG RCA Team
EOF
```

---

## Client-Side Installation

### Step 1: Receive Installation Package

```bash
# Client receives acme-client-installation.tar.gz

# Extract package
tar xzf acme-client-installation.tar.gz

# Contents:
# - acme-client-values.yaml
# - acme-client-README.md
```

### Step 2: Pre-Installation Checks

```bash
# Verify Kubernetes access
kubectl cluster-info
kubectl get nodes

# Verify Helm is installed
helm version

# Check available resources
kubectl top nodes

# Test outbound connectivity to server
curl -v https://api.kg-rca.yourcompany.com/healthz

# Expected output:
# ok

# Test Kafka connectivity
nc -zv kafka.kg-rca.yourcompany.com 9092

# Expected output:
# Connection to kafka.kg-rca.yourcompany.com 9092 port [tcp/*] succeeded!
```

### Step 3: Install Helm Chart

```bash
# Add Helm repository
helm repo add kg-rca https://charts.kg-rca.yourcompany.com
helm repo update

# Verify chart is available
helm search repo kg-rca

# Expected output:
# NAME                    CHART VERSION   APP VERSION     DESCRIPTION
# kg-rca/kg-rca-agent     1.0.0           1.0.0           KG RCA Agent for Kubernetes

# Install chart
helm install kg-rca-agent kg-rca/kg-rca-agent \
  --namespace kg-rca \
  --create-namespace \
  --values acme-client-values.yaml \
  --wait \
  --timeout 10m

# Expected output:
# NAME: kg-rca-agent
# LAST DEPLOYED: Thu Jan  9 11:00:00 2025
# NAMESPACE: kg-rca
# STATUS: deployed
# REVISION: 1
# NOTES:
# Thank you for installing kg-rca-agent!
# ...
```

### Step 4: Verify Installation

```bash
# Check all pods are running
kubectl get pods -n kg-rca

# Expected output:
# NAME                                READY   STATUS    RESTARTS   AGE
# kg-rca-state-watcher-xxxxx          1/1     Running   0          2m
# kg-rca-vector-xxxxx                 1/1     Running   0          2m
# kg-rca-vector-yyyyy                 1/1     Running   0          2m
# kg-rca-event-exporter-xxxxx         1/1     Running   0          2m
# kg-rca-alert-receiver-xxxxx         1/1     Running   0          2m

# Check services
kubectl get svc -n kg-rca

# Expected output:
# NAME                    TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)
# kg-rca-alert-receiver   ClusterIP   10.100.10.10    <none>        8080/TCP

# Check ConfigMaps
kubectl get configmap -n kg-rca

# Expected output:
# NAME                DATA   AGE
# kg-rca-config       5      2m
# vector-config       1      2m

# Check Secrets
kubectl get secrets -n kg-rca

# Expected output:
# NAME                TYPE                                  DATA   AGE
# kg-rca-credentials  Opaque                                4      2m
```

---

## Verification

### Step 1: Check Agent Logs

```bash
# State Watcher logs
kubectl logs -n kg-rca deployment/kg-rca-state-watcher --tail=50

# Expected output:
# 2025-01-09T11:00:00Z INFO  Connected to Kafka broker: kafka.kg-rca.yourcompany.com:9092
# 2025-01-09T11:00:01Z INFO  Authenticated with SASL/SCRAM-SHA-512
# 2025-01-09T11:00:02Z INFO  Watching namespaces: [default, kube-system, ...]
# 2025-01-09T11:00:03Z INFO  Sent resource state: Pod/default/nginx-deployment-xxxxx
# 2025-01-09T11:00:04Z INFO  Sent resource state: Deployment/default/nginx-deployment

# Vector logs
kubectl logs -n kg-rca daemonset/kg-rca-vector --tail=50

# Expected output:
# 2025-01-09T11:00:00Z INFO  vector::sources::kubernetes_logs: Kubernetes logs source started
# 2025-01-09T11:00:01Z INFO  vector::sinks::kafka: Connected to Kafka
# 2025-01-09T11:00:02Z INFO  vector::sinks::kafka: Sent 42 log messages to client-acme-abc123.logs.normalized

# Event Exporter logs
kubectl logs -n kg-rca deployment/kg-rca-event-exporter --tail=50

# Expected output:
# 2025-01-09T11:00:00Z INFO  Starting Kubernetes Event Exporter
# 2025-01-09T11:00:01Z INFO  Connected to Kafka: kafka.kg-rca.yourcompany.com:9092
# 2025-01-09T11:00:02Z INFO  Exported event: Pod/default/nginx-deployment-xxxxx/Scheduled
```

### Step 2: Verify Data Flow (Server-Side)

```bash
# Check Kafka topics have data
kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group kg-builder

# Expected output:
# TOPIC                                    PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# client-acme-abc123.events.normalized     0          142             142             0
# client-acme-abc123.logs.normalized       0          1523            1523            0
# client-acme-abc123.state.k8s.resource    0          87              87              0

# Check Neo4j database has nodes
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (r:Resource) RETURN count(r) as resource_count;"

# Expected output:
# resource_count
# --------------
# 45

kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (e:Episodic) RETURN count(e) as episodic_count;"

# Expected output:
# episodic_count
# --------------
# 123
```

### Step 3: Test API Access (Client-Side)

```bash
# Test API connectivity
API_KEY="kg_client-acme-abc123_9f4b2e8d1c7a6f3e5b8d2c1a9f4b2e8d"

# Get statistics
curl -H "X-API-Key: $API_KEY" \
  https://api.kg-rca.yourcompany.com/api/v1/stats

# Expected output:
# {
#   "client_id": "client-acme-abc123",
#   "total_resources": 45,
#   "total_episodic": 123,
#   "total_incidents": 3,
#   "rca_links": 18,
#   "last_event_time": "2025-01-09T11:05:00Z"
# }

# Get resources
curl -H "X-API-Key: $API_KEY" \
  "https://api.kg-rca.yourcompany.com/api/v1/resources?limit=5"

# Expected output:
# {
#   "resources": [
#     {
#       "id": "res-001",
#       "name": "nginx-deployment",
#       "namespace": "default",
#       "kind": "Deployment",
#       "cluster": "production"
#     },
#     ...
#   ],
#   "total": 45
# }

# Search for events
curl -H "X-API-Key: $API_KEY" \
  "https://api.kg-rca.yourcompany.com/api/v1/search/semantic?query=pod%20crash"

# Expected output:
# {
#   "results": [
#     {
#       "event_id": "evt-123",
#       "message": "Pod backend-pod-abc crashed with exit code 137",
#       "severity": "error",
#       "timestamp": "2025-01-09T10:55:00Z",
#       "resource": "backend-pod-abc",
#       "relevance_score": 0.95
#     },
#     ...
#   ]
# }
```

---

## Testing Data Flow

### Test 1: Trigger a Pod Restart

```bash
# Create test deployment (client-side)
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-rca-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: test-rca
  template:
    metadata:
      labels:
        app: test-rca
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "200m"
EOF

# Wait for pods to be running
kubectl wait --for=condition=ready pod -l app=test-rca -n default --timeout=60s

# Trigger a restart by deleting pod
kubectl delete pod -l app=test-rca -n default --wait=false

# Watch State Watcher logs
kubectl logs -n kg-rca deployment/kg-rca-state-watcher -f

# Expected output:
# 2025-01-09T11:10:00Z INFO  Detected pod deletion: test-rca-app-xxxxx
# 2025-01-09T11:10:01Z INFO  Sent event to Kafka: client-acme-abc123.events.normalized
# 2025-01-09T11:10:02Z INFO  Detected pod creation: test-rca-app-yyyyy
# 2025-01-09T11:10:03Z INFO  Sent event to Kafka: client-acme-abc123.events.normalized

# Verify on server-side (after ~30 seconds)
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (e:Episodic)-[:ABOUT]->(r:Resource {name: 'test-rca-app'})
   RETURN e.message, e.timestamp, r.kind
   ORDER BY e.timestamp DESC
   LIMIT 5;"

# Expected output:
# e.message                     | e.timestamp  | r.kind
# ------------------------------|--------------|------------
# "Pod test-rca-app-yyy created"| 1704796203   | Deployment
# "Pod test-rca-app-xxx deleted"| 1704796201   | Deployment
```

### Test 2: Generate Logs

```bash
# Create pod with logging (client-side)
kubectl run log-generator --image=busybox --restart=Never -- sh -c \
  "while true; do echo 'Test log message from KG RCA test'; sleep 5; done"

# Watch Vector logs
kubectl logs -n kg-rca daemonset/kg-rca-vector -f | grep "log-generator"

# Expected output:
# 2025-01-09T11:15:00Z INFO  Collected log from pod: log-generator
# 2025-01-09T11:15:05Z INFO  Sent 1 log to Kafka: client-acme-abc123.logs.normalized

# Verify on server-side (after ~30 seconds)
kubectl exec -n kg-rca-server kafka-0 -- kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic client-acme-abc123.logs.normalized \
  --from-beginning \
  --max-messages 5

# Expected output (JSON):
# {"client_id":"client-acme-abc123","pod":"log-generator","message":"Test log message...","timestamp":...}
```

### Test 3: Create Kubernetes Event

```bash
# Create a failing deployment (client-side)
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: failing-app
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: failing
  template:
    metadata:
      labels:
        app: failing
    spec:
      containers:
      - name: app
        image: nonexistent-image:latest  # This will fail to pull
EOF

# Wait for ImagePullBackOff event
kubectl get events -n default | grep failing-app

# Expected output:
# 2m  Warning  Failed  pod/failing-app-xxxxx  Failed to pull image "nonexistent-image:latest"

# Watch Event Exporter logs
kubectl logs -n kg-rca deployment/kg-rca-event-exporter -f

# Expected output:
# 2025-01-09T11:20:00Z INFO  Exported event: Pod/default/failing-app-xxxxx/Failed
# 2025-01-09T11:20:01Z INFO  Sent to Kafka: client-acme-abc123.events.normalized

# Verify RCA link creation on server (after ~1 minute)
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (inc:Incident {resource: 'failing-app'})<-[r:POTENTIAL_CAUSE]-(cause:Episodic)
   RETURN cause.message, r.confidence
   ORDER BY r.confidence DESC
   LIMIT 5;"

# Expected output:
# cause.message                        | r.confidence
# -------------------------------------|-------------
# "Failed to pull image nonexistent..."| 0.95
```

---

## Troubleshooting

### Issue 1: Agents Not Connecting to Kafka

```bash
# Check State Watcher logs
kubectl logs -n kg-rca deployment/kg-rca-state-watcher

# Common errors:
# - "Connection refused" → Check Kafka LoadBalancer IP/hostname
# - "Authentication failed" → Check SASL credentials
# - "Topic not found" → Check topic creation on server

# Solution: Verify Kafka connectivity
kubectl run -n kg-rca test-kafka --image=confluentinc/cp-kafka:latest --rm -it --restart=Never -- \
  kafka-console-producer.sh \
  --bootstrap-server kafka.kg-rca.yourcompany.com:9092 \
  --topic client-acme-abc123.events.normalized \
  --producer-property security.protocol=SASL_PLAINTEXT \
  --producer-property sasl.mechanism=SCRAM-SHA-512 \
  --producer-property sasl.jaas.config='org.apache.kafka.common.security.scram.ScramLoginModule required username="client-acme-abc123" password="YOUR_PASSWORD";'

# Type test message and press Ctrl+D
# If successful, connection is working
```

### Issue 2: No Data in Neo4j

```bash
# Check Graph Builder logs (server-side)
kubectl logs -n kg-rca-server deployment/graph-builder --tail=100

# Common issues:
# - Consumer lag too high
# - Neo4j connection errors
# - Message parsing errors

# Check consumer lag
kubectl exec -n kg-rca-server kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group kg-builder

# If lag is high (>1000), check Graph Builder CPU/memory
kubectl top pods -n kg-rca-server -l app=graph-builder

# If resources are high, scale up
kubectl scale deployment graph-builder -n kg-rca-server --replicas=10
```

### Issue 3: API Requests Failing

```bash
# Test API key validity
curl -v -H "X-API-Key: $API_KEY" \
  https://api.kg-rca.yourcompany.com/api/v1/stats

# Common responses:
# - 401 Unauthorized → API key invalid or expired
# - 429 Too Many Requests → Rate limit exceeded
# - 500 Internal Server Error → Server issue

# Check API logs (server-side)
kubectl logs -n kg-rca-server deployment/kg-api --tail=100

# Verify API key in database
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "SELECT client_id, key_prefix, created_at, last_used_at FROM api_keys WHERE client_id = 'client-acme-abc123';"
```

### Issue 4: RCA Links Not Generating

```bash
# Check if incidents are being created
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p PASSWORD \
  -d client_acme_abc123_kg \
  "MATCH (inc:Incident) RETURN count(inc) as incident_count;"

# If count is 0, no error-level events detected
# Trigger a test error:
kubectl run error-pod --image=busybox --restart=Never -- sh -c "exit 1"

# Wait 1 minute, then check again
# If incidents exist but no RCA links, check Graph Builder logs
kubectl logs -n kg-rca-server deployment/graph-builder | grep "RCA"

# Check RCA configuration
kubectl exec -n kg-rca-server deployment/graph-builder -- env | grep RCA

# Expected:
# RCA_WINDOW_MIN=15
# INCIDENT_CLUSTERING_ENABLED=true
```

---

## Client Offboarding

### Step 1: Suspend Client Access

```bash
# Update client status
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "UPDATE clients SET status = 'suspended' WHERE id = 'client-acme-abc123';"

# Revoke Kafka ACLs
kubectl exec -n kg-rca-server kafka-0 -- kafka-acls.sh \
  --bootstrap-server kafka:9092 \
  --remove \
  --allow-principal User:client-acme-abc123 \
  --operation All \
  --topic "*" \
  --force

# Delete Kafka SASL credentials
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --delete-config SCRAM-SHA-512 \
  --entity-type users \
  --entity-name client-acme-abc123
```

### Step 2: Export Client Data (Optional)

```bash
# Export Neo4j database
kubectl exec -n kg-rca-server neo4j-0 -- neo4j-admin dump \
  --database=client_acme_abc123_kg \
  --to=/backups/client_acme_abc123_kg.dump

# Copy dump file
kubectl cp kg-rca-server/neo4j-0:/backups/client_acme_abc123_kg.dump \
  ./client_acme_abc123_kg.dump

# Send to client via secure channel
```

### Step 3: Delete Client Data

```bash
# Delete Neo4j database (after 30-day grace period)
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell -u neo4j -p PASSWORD \
  "DROP DATABASE client_acme_abc123_kg;"

# Delete Kafka topics
TOPICS=(
  "client-acme-abc123.events.normalized"
  "client-acme-abc123.logs.normalized"
  "client-acme-abc123.state.k8s.resource"
  "client-acme-abc123.state.k8s.topology"
  "client-acme-abc123.alerts.raw"
)

for TOPIC in "${TOPICS[@]}"; do
  kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
    --bootstrap-server kafka:9092 \
    --delete \
    --topic "$TOPIC"
done

# Archive and delete client record
kubectl exec -n kg-rca-server postgresql-0 -- psql -U billing -c \
  "UPDATE clients SET status = 'deleted', updated_at = NOW() WHERE id = 'client-acme-abc123';"
```

---

## Onboarding Checklist

**Server-Side**:
- [ ] Client record created in PostgreSQL
- [ ] API key generated and stored
- [ ] Kafka SASL credentials created
- [ ] Neo4j database created
- [ ] Kafka topics created
- [ ] Kafka ACLs configured
- [ ] Installation package generated
- [ ] Welcome email sent to client

**Client-Side**:
- [ ] Installation package received
- [ ] Pre-installation checks passed
- [ ] Helm chart installed
- [ ] All pods running
- [ ] Connectivity verified
- [ ] Data flow to server confirmed
- [ ] API access tested
- [ ] Test scenarios executed

---

**Onboarding Complete!**

Your client is now successfully onboarded and sending data to the KG RCA platform.

**Next Steps**:
- Monitor client metrics in Grafana
- Review RCA quality metrics
- Schedule follow-up call with client
- Set up billing in Stripe

**Next**: [Operations Guide](03-OPERATIONS.md)

---

**Document Version**: 1.0.0
**Maintained By**: Platform Engineering Team
**Last Review**: 2025-01-09
