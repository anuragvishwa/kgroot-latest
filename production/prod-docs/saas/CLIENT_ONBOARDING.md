# Client Onboarding Guide

Complete guide for onboarding new clients to your KG RCA SaaS platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Step 1: Create Client Account](#step-1-create-client-account)
4. [Step 2: Generate Client Credentials](#step-2-generate-client-credentials)
5. [Step 3: Prepare Client Installation](#step-3-prepare-client-installation)
6. [Step 4: Client Installs Agents](#step-4-client-installs-agents)
7. [Step 5: Verify Data Flow](#step-5-verify-data-flow)
8. [Step 6: Grant Dashboard Access](#step-6-grant-dashboard-access)
9. [Troubleshooting](#troubleshooting)
10. [Client Offboarding](#client-offboarding)

---

## Overview

**Your SaaS Model**:
- **YOU host**: Neo4j, Kafka, Graph Builder, KG API, Embedding Service, Billing
- **CLIENT installs**: Lightweight agents (state-watcher, vector, event-exporter)
- **CLIENT pays**: Based on usage (events, queries, storage)

**Onboarding Time**: ~30 minutes per client

---

## Prerequisites

### Your Server Must Be Running

```bash
# Verify server components
kubectl get pods -n kg-rca-server

# Expected output:
# neo4j-0, neo4j-1, neo4j-2          Running
# kafka-0, kafka-1, kafka-2          Running
# graph-builder-xxx                  Running
# kg-api-xxx                         Running
# billing-service-xxx                Running
```

### Client Requirements

- **Kubernetes cluster**: v1.24+
- **Helm**: v3.8+
- **kubectl**: Configured with cluster access
- **Network access**: To your server (ports 9092, 443)

---

## Step 1: Create Client Account

### 1.1 Register Client

```bash
# Create new client
curl -X POST https://api.kg-rca.your-company.com/admin/clients \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "environment": "production",
    "region": "us-east-1",
    "plan": "pro",
    "contact": {
      "email": "ops@acmecorp.com",
      "name": "John Doe"
    },
    "metadata": {
      "company_size": "500-1000",
      "industry": "fintech"
    }
  }'

# Response:
{
  "client_id": "acme-prod-us-east-1",
  "api_key": "kg_live_abc123def456...",
  "created_at": "2025-01-15T10:30:00Z",
  "status": "active"
}
```

**Save the response!** You'll need `client_id` and `api_key`.

### 1.2 Select Pricing Plan

| Plan | Price | Events/Day | RCA Queries | Storage | API Rate Limit |
|------|-------|------------|-------------|---------|----------------|
| **Free** | $0 | 10K | 100 | 1 GB | 100/min |
| **Basic** | $99/mo | 100K | 1K | 10 GB | 1K/min |
| **Pro** | $499/mo | 1M | 10K | 100 GB | 10K/min |
| **Enterprise** | Custom | Unlimited | Unlimited | Custom | Custom |

---

## Step 2: Generate Client Credentials

### 2.1 Create Neo4j Database

```bash
# SSH into Neo4j pod
kubectl exec -n kg-rca-server neo4j-0 -it -- bash

# Create client database
cypher-shell -u neo4j -p $NEO4J_PASSWORD

CREATE DATABASE acme_prod_us_east_1;
STOP DATABASE acme_prod_us_east_1;
START DATABASE acme_prod_us_east_1;

# Create indexes (use client database)
USE acme_prod_us_east_1;

CREATE CONSTRAINT FOR (r:Resource) REQUIRE r.uid IS UNIQUE;
CREATE CONSTRAINT FOR (e:Episodic) REQUIRE e.eid IS UNIQUE;
CREATE INDEX FOR (e:Episodic) ON (e.event_time);
CREATE INDEX FOR (e:Episodic) ON (e.severity);

# Create vector index for embeddings
CALL db.index.vector.createNodeIndex(
  'episodic_embeddings',
  'Episodic',
  'embedding',
  384,
  'cosine'
);
```

### 2.2 Create Kafka Topics

```bash
# SSH into Kafka pod
kubectl exec -n kg-rca-server kafka-0 -it -- bash

# Create client-specific topics
for topic in \
  acme-prod-us-east-1.events.normalized \
  acme-prod-us-east-1.state.k8s.resource \
  acme-prod-us-east-1.state.k8s.topology \
  acme-prod-us-east-1.logs.normalized \
  acme-prod-us-east-1.alerts.raw
do
  kafka-topics.sh --bootstrap-server localhost:9092 \
    --create \
    --topic $topic \
    --partitions 12 \
    --replication-factor 3 \
    --config retention.ms=604800000 \
    --config compression.type=lz4
done

# Verify
kafka-topics.sh --bootstrap-server localhost:9092 --list | grep acme-prod
```

### 2.3 Create Kafka Credentials (SASL)

```bash
# Generate Kafka password
KAFKA_PASSWORD=$(openssl rand -base64 32)

# Add SASL user
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --add-config "SCRAM-SHA-256=[password=$KAFKA_PASSWORD]" \
  --entity-type users \
  --entity-name acme-prod-us-east-1

# Save credentials securely
echo "Client ID: acme-prod-us-east-1" >> clients/acme-prod-credentials.txt
echo "Kafka Password: $KAFKA_PASSWORD" >> clients/acme-prod-credentials.txt
```

### 2.4 Generate TLS Certificates (Optional)

```bash
# Generate client certificate for Kafka TLS
openssl genrsa -out acme-prod-client.key 2048

openssl req -new -key acme-prod-client.key \
  -out acme-prod-client.csr \
  -subj "/CN=acme-prod-us-east-1"

openssl x509 -req -in acme-prod-client.csr \
  -CA ca.crt -CAkey ca.key \
  -CAcreateserial \
  -out acme-prod-client.crt \
  -days 365

# Save certificates
cat ca.crt > acme-prod-ca.pem
```

---

## Step 3: Prepare Client Installation

### 3.1 Create Client Values File

```bash
# Create custom values for client
cat > acme-prod-values.yaml <<EOF
# Client Configuration
client:
  id: "acme-prod-us-east-1"
  apiKey: "kg_live_abc123def456..."
  serverUrl: "https://api.kg-rca.your-company.com"

  name: "Acme Corp Production"
  environment: "production"
  region: "us-east-1"

  # Kafka endpoint (YOUR server)
  kafka:
    brokers: "kafka.kg-rca.your-company.com:9092"
    tls:
      enabled: true
      ca: |
        -----BEGIN CERTIFICATE-----
        [YOUR CA CERTIFICATE]
        -----END CERTIFICATE-----
    sasl:
      enabled: true
      mechanism: SCRAM-SHA-256
      username: "acme-prod-us-east-1"
      password: "$KAFKA_PASSWORD"

# State Watcher - Monitor K8s resources
stateWatcher:
  enabled: true
  image:
    repository: your-registry.com/state-watcher
    tag: v1.0.0
  resources:
    requests:
      cpu: 200m
      memory: 512Mi
  config:
    watchResources:
      - pods
      - services
      - deployments
      - nodes
    watchNamespaces: []  # All namespaces
    excludeNamespaces:
      - kube-system

# Vector - Log collection
vector:
  enabled: true
  daemonset:
    enabled: true
  resources:
    requests:
      cpu: 100m
      memory: 256Mi

# K8s Event Exporter
eventExporter:
  enabled: true
  resources:
    requests:
      cpu: 100m
      memory: 256Mi

# Prometheus Remote Write (if client has Prometheus)
prometheusRemoteWrite:
  enabled: false

# Alertmanager Webhook (if client has Alertmanager)
alertmanagerWebhook:
  enabled: false

# Health Check Agent
healthCheck:
  enabled: true
  config:
    reportInterval: 5m
EOF
```

### 3.2 Package for Client

```bash
# Create client onboarding package
mkdir -p client-packages/acme-prod/

cp acme-prod-values.yaml client-packages/acme-prod/
cp production/helm-chart/client/kg-rca-agent client-packages/acme-prod/ -r

# Create installation script
cat > client-packages/acme-prod/install.sh <<'SCRIPT'
#!/bin/bash
set -e

echo "Installing KG RCA Agent for Acme Corp..."

# Install Helm chart
helm upgrade --install kg-rca-agent ./kg-rca-agent \
  --namespace kg-rca \
  --create-namespace \
  --values acme-prod-values.yaml \
  --wait \
  --timeout 5m

echo "✓ Installation complete!"
echo ""
echo "Verify installation:"
echo "  kubectl get pods -n kg-rca"
SCRIPT

chmod +x client-packages/acme-prod/install.sh

# Create README for client
cat > client-packages/acme-prod/README.md <<'README'
# KG RCA Agent Installation

## Prerequisites
- Kubernetes cluster v1.24+
- Helm v3.8+
- kubectl configured with cluster admin access

## Installation
```bash
./install.sh
```

## Verification
```bash
kubectl get pods -n kg-rca
```

All pods should be in `Running` state.

## Support
- Email: support@your-company.com
- Dashboard: https://dashboard.kg-rca.your-company.com
- Docs: https://docs.kg-rca.your-company.com
README

# Create ZIP for client
cd client-packages/
zip -r acme-prod-installation.zip acme-prod/
cd ..

echo "✓ Client package ready: client-packages/acme-prod-installation.zip"
```

### 3.3 Send to Client

```bash
# Email to client
cat > email-to-client.txt <<EMAIL
Subject: KG RCA Installation Package - Acme Corp

Hi John,

Welcome to KG RCA! Your account is ready.

**Installation Package**: See attached acme-prod-installation.zip

**Your Credentials**:
- Client ID: acme-prod-us-east-1
- API Key: kg_live_abc123def456... (see values file)
- Dashboard: https://dashboard.kg-rca.your-company.com

**Installation Steps**:
1. Extract the ZIP file
2. Review acme-prod-values.yaml
3. Run ./install.sh

**What Gets Installed**:
- State Watcher (monitors K8s resources)
- Vector (collects logs)
- Event Exporter (captures K8s events)
- Health Check Agent

**Data Flow**:
Your cluster → YOUR server → Neo4j Knowledge Graph

**Next Steps**:
1. Install agents in your cluster
2. Verify data flow (see README)
3. Access dashboard with your API key
4. Run your first RCA query!

Questions? Reply to this email or visit docs.kg-rca.your-company.com

Best regards,
KG RCA Team
EMAIL
```

---

## Step 4: Client Installs Agents

### 4.1 Client Runs Installation

```bash
# Client extracts and runs
unzip acme-prod-installation.zip
cd acme-prod/
./install.sh

# Output:
# Installing KG RCA Agent for Acme Corp...
# Release "kg-rca-agent" has been installed
# ✓ Installation complete!
```

### 4.2 Client Verifies Pods

```bash
kubectl get pods -n kg-rca

# Expected:
# NAME                            READY   STATUS    RESTARTS   AGE
# state-watcher-xxx               1/1     Running   0          2m
# vector-xxx                      1/1     Running   0          2m
# event-exporter-xxx              1/1     Running   0          2m
# health-check-xxx                1/1     Running   0          2m
```

---

## Step 5: Verify Data Flow

### 5.1 Verify Kafka Topics (Your Server)

```bash
# Check Kafka consumer lag
kubectl exec -n kg-rca-server kafka-0 -- \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group graph-builder

# Look for acme-prod topics with LAG decreasing
```

### 5.2 Verify Neo4j Data (Your Server)

```bash
# Query client's Neo4j database
kubectl exec -n kg-rca-server neo4j-0 -it -- cypher-shell \
  -u neo4j -p $NEO4J_PASSWORD -d acme_prod_us_east_1

USE acme_prod_us_east_1;

# Check resource nodes
MATCH (r:Resource) RETURN r.kind, count(*);

# Check episodic events
MATCH (e:Episodic) RETURN e.severity, count(*) ORDER BY count(*) DESC;

# Should see data within 5-10 minutes
```

### 5.3 Test API Access

```bash
# Client tests API with their key
curl -X GET https://api.kg-rca.your-company.com/api/v1/resources \
  -H "Authorization: Bearer kg_live_abc123def456..."

# Should return client's resources
{
  "client_id": "acme-prod-us-east-1",
  "resources": [
    {"kind": "Pod", "count": 150},
    {"kind": "Deployment", "count": 42},
    ...
  ]
}
```

### 5.4 Test Dashboard Access

```bash
# Client logs into dashboard
https://dashboard.kg-rca.your-company.com

# Login with:
# - Email: ops@acmecorp.com
# - API Key: kg_live_abc123def456...

# Verify:
# - Resource topology visible
# - Events streaming in
# - RCA queries work
```

---

## Step 6: Grant Dashboard Access

### 6.1 Create Dashboard User

```bash
# Create Grafana user for client
kubectl exec -n kg-rca-server grafana-0 -- \
  grafana-cli admin reset-admin-password $CLIENT_PASSWORD

# Or via API:
curl -X POST http://grafana.kg-rca-server.svc.cluster.local:3000/api/admin/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "email": "ops@acmecorp.com",
    "login": "acme-prod-us-east-1",
    "password": "'$CLIENT_PASSWORD'",
    "OrgId": 2
  }'

# Create organization for client
curl -X POST http://grafana.kg-rca-server.svc.cluster.local:3000/api/orgs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp"
  }'

# Assign dashboards with data source filtering
# (Only show client's own data)
```

### 6.2 Configure Data Source Filtering

```bash
# Grafana dashboard JSON
cat > dashboards/acme-prod-dashboard.json <<'JSON'
{
  "dashboard": {
    "title": "Acme Corp - KG RCA Overview",
    "panels": [
      {
        "title": "Events Ingested",
        "targets": [
          {
            "expr": "sum(kg_messages_processed_total{client_id=\"acme-prod-us-east-1\"})"
          }
        ]
      },
      {
        "title": "RCA Queries",
        "targets": [
          {
            "expr": "sum(kg_rca_queries_total{client_id=\"acme-prod-us-east-1\"})"
          }
        ]
      }
    ]
  }
}
JSON

# Import dashboard
curl -X POST http://grafana:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @dashboards/acme-prod-dashboard.json
```

---

## Troubleshooting

### Problem 1: Pods Not Starting

```bash
# Check pod logs
kubectl logs -n kg-rca state-watcher-xxx

# Common issues:
# - Wrong API key → Update values.yaml, helm upgrade
# - Network policy blocking → Check network policies
# - Resource limits → Increase requests/limits
```

### Problem 2: No Data in Neo4j

```bash
# Check Kafka topics
kubectl exec -n kg-rca-server kafka-0 -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic acme-prod-us-east-1.events.normalized \
  --from-beginning \
  --max-messages 10

# If no messages:
# - Check client pod logs
# - Verify SASL credentials
# - Check firewall rules

# If messages but no Neo4j data:
# - Check graph-builder logs
# - Verify Neo4j database created
# - Check graph-builder consuming from client topics
```

### Problem 3: Authentication Failures

```bash
# Test Kafka authentication
kubectl exec -n kg-rca-server kafka-0 -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic acme-prod-us-east-1.events.normalized \
  --consumer-property security.protocol=SASL_SSL \
  --consumer-property sasl.mechanism=SCRAM-SHA-256 \
  --consumer-property sasl.jaas.config="org.apache.kafka.common.security.scram.ScramLoginModule required username='acme-prod-us-east-1' password='$KAFKA_PASSWORD';"

# If fails:
# - Verify SASL user created
# - Check password matches
# - Verify TLS certificates
```

### Problem 4: Dashboard Not Showing Data

```bash
# Check Prometheus is scraping client metrics
curl http://prometheus.kg-rca-server.svc.cluster.local:9090/api/v1/query \
  -d 'query=kg_messages_processed_total{client_id="acme-prod-us-east-1"}'

# If no metrics:
# - Verify graph-builder is processing client topics
# - Check Prometheus scrape configs include client_id label
```

### Problem 5: High Consumer Lag

```bash
# Check consumer lag
kubectl exec -n kg-rca-server kafka-0 -- \
  kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group graph-builder

# If lag is high (>10k):
# - Scale up graph-builder replicas
# - Check graph-builder pod resources
# - Verify Neo4j is not bottleneck
```

---

## Client Offboarding

### When Client Cancels Subscription

```bash
# 1. Stop client agents (client does this)
helm uninstall kg-rca-agent -n kg-rca

# 2. Mark client as inactive (your server)
curl -X PATCH https://api.kg-rca.your-company.com/admin/clients/acme-prod-us-east-1 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"status": "inactive"}'

# 3. Stop processing client data
# - Remove client topics from graph-builder config
# - Revoke API key

# 4. Retain data for 30 days (for potential reactivation)
# - Keep Neo4j database
# - Keep Kafka topics (will auto-delete after retention period)

# 5. After 30 days, delete data
# - Drop Neo4j database
# - Delete Kafka topics
# - Archive billing data (keep for 7 years for compliance)

# Drop Neo4j database
kubectl exec -n kg-rca-server neo4j-0 -it -- cypher-shell \
  -u neo4j -p $NEO4J_PASSWORD

DROP DATABASE acme_prod_us_east_1;

# Delete Kafka topics
kubectl exec -n kg-rca-server kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 \
  --delete --topic "acme-prod-us-east-1.*"

# Revoke SASL user
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --delete-config "SCRAM-SHA-256" \
  --entity-type users \
  --entity-name acme-prod-us-east-1
```

---

## Checklist: Successful Onboarding

- [ ] Client account created in billing system
- [ ] Neo4j database created with indexes
- [ ] Kafka topics created (5 topics per client)
- [ ] SASL credentials generated
- [ ] API key generated
- [ ] Client installation package created
- [ ] Client package sent to client
- [ ] Client installed agents successfully
- [ ] Agents pods running in client cluster
- [ ] Data flowing to Kafka topics (verify lag)
- [ ] Data appearing in Neo4j database
- [ ] Client can access API with their key
- [ ] Client can log into dashboard
- [ ] Dashboard shows client's data (filtered)
- [ ] RCA queries working for client
- [ ] Health check agent reporting
- [ ] Client added to billing system
- [ ] Client documentation sent

**Average Time**: 30 minutes per client

---

## Automation Ideas

### Script: Automated Onboarding

```bash
#!/bin/bash
# onboard-client.sh
# Usage: ./onboard-client.sh "Acme Corp" "ops@acmecorp.com" "pro"

CLIENT_NAME=$1
CLIENT_EMAIL=$2
PLAN=$3

# Generate client ID
CLIENT_ID=$(echo "$CLIENT_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')-prod-$(uuidgen | cut -d- -f1)

echo "Onboarding $CLIENT_NAME with ID: $CLIENT_ID"

# 1. Create account via API
API_RESPONSE=$(curl -s -X POST https://api.kg-rca.your-company.com/admin/clients \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d "{\"name\": \"$CLIENT_NAME\", \"email\": \"$CLIENT_EMAIL\", \"plan\": \"$PLAN\"}")

API_KEY=$(echo $API_RESPONSE | jq -r '.api_key')

# 2. Create Neo4j database
NEO4J_DB=$(echo $CLIENT_ID | tr '-' '_')
kubectl exec -n kg-rca-server neo4j-0 -- cypher-shell \
  -u neo4j -p $NEO4J_PASSWORD \
  "CREATE DATABASE $NEO4J_DB; START DATABASE $NEO4J_DB;"

# 3. Create Kafka topics
for suffix in events.normalized state.k8s.resource state.k8s.topology logs.normalized alerts.raw; do
  kubectl exec -n kg-rca-server kafka-0 -- kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create --topic "$CLIENT_ID.$suffix" \
    --partitions 12 --replication-factor 3
done

# 4. Generate Kafka credentials
KAFKA_PASSWORD=$(openssl rand -base64 32)
kubectl exec -n kg-rca-server kafka-0 -- kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter --add-config "SCRAM-SHA-256=[password=$KAFKA_PASSWORD]" \
  --entity-type users --entity-name $CLIENT_ID

# 5. Create client package
./create-client-package.sh $CLIENT_ID $API_KEY $KAFKA_PASSWORD

echo "✓ Client $CLIENT_NAME onboarded successfully!"
echo "Client ID: $CLIENT_ID"
echo "API Key: $API_KEY"
echo "Package: client-packages/$CLIENT_ID-installation.zip"
```

---

## Support Resources

- **Documentation**: https://docs.kg-rca.your-company.com
- **Support Email**: support@your-company.com
- **Status Page**: https://status.kg-rca.your-company.com
- **Community Slack**: https://slack.kg-rca.your-company.com

---

## Next: Billing Setup

See [BILLING_SETUP.md](BILLING_SETUP.md) for:
- Stripe integration
- Usage tracking
- Invoice generation
- Payment processing
