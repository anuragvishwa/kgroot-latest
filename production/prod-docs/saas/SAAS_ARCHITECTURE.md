# KG RCA SaaS Architecture Guide

## 🏗️ Multi-Tenant Architecture

### Overview

**YOU** (Service Provider) host the central infrastructure:
- Neo4j (knowledge graph)
- Kafka (message broker)
- Graph Builder (RCA engine)
- KG API (REST endpoints)
- Billing system

**CLIENTS** install lightweight agents in their clusters:
- State Watcher (K8s resource monitoring)
- Vector (log collection)
- K8s Event Exporter (event collection)

---

## 📐 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  YOUR SERVER (SaaS Platform)                 │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              API Gateway (Kong)                       │   │
│  │  - Client authentication                              │   │
│  │  - Rate limiting (per plan)                          │   │
│  │  - Request routing                                    │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                           │
│  ┌────────────────┴─────────────────────────────────────┐   │
│  │           KG API (Multi-tenant REST)                  │   │
│  │  /api/v1/search/semantic?client_id=xxx               │   │
│  │  /api/v1/rca?client_id=xxx                           │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                           │
│  ┌────────────────┴─────────────────────────────────────┐   │
│  │    Neo4j (Multi-tenant - database per client)        │   │
│  │  - Database: client1_kg                               │   │
│  │  - Database: client2_kg                               │   │
│  │  - Database: client3_kg                               │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                           │
│  ┌────────────────┴─────────────────────────────────────┐   │
│  │         Kafka (Multi-tenant - topic per client)      │   │
│  │  Topics:                                              │   │
│  │  - client1.events.normalized                         │   │
│  │  - client1.logs.normalized                           │   │
│  │  - client1.state.k8s.resource                        │   │
│  │  - client2.events.normalized                         │   │
│  │  - client2.logs.normalized                           │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                           │
│  ┌────────────────┴─────────────────────────────────────┐   │
│  │       Graph Builder (Multi-tenant processor)          │   │
│  │  - Consumes: client*.events.normalized                │   │
│  │  - Writes to: client-specific Neo4j database          │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │          Billing Service (Usage tracking)             │   │
│  │  - Events ingested per client                         │   │
│  │  - RCA queries per client                             │   │
│  │  - Storage used per client                            │   │
│  │  - API calls per client                               │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │          PostgreSQL (Client metadata)                 │   │
│  │  Tables:                                               │   │
│  │  - clients (id, name, plan, status)                   │   │
│  │  - api_keys (client_id, key, permissions)            │   │
│  │  - subscriptions (client_id, plan, billing_cycle)    │   │
│  │  - usage_metrics (client_id, metric, value, date)    │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         ▲
                         │ HTTPS + Kafka (TLS + SASL)
        ┌────────────────┼────────────────┐
        │                │                │
┌───────┴────────┐ ┌─────┴──────┐ ┌──────┴────────┐
│ CLIENT 1       │ │ CLIENT 2   │ │ CLIENT 3      │
│ (Acme Corp)    │ │ (Beta Inc) │ │ (Gamma LLC)   │
├────────────────┤ ├────────────┤ ├───────────────┤
│ State Watcher  │ │ State      │ │ State Watcher │
│ Vector Logs    │ │ Watcher    │ │ Vector Logs   │
│ Event Exporter │ │ Vector     │ │ Event Exporter│
└────────────────┘ └────────────┘ └───────────────┘
   K8s Cluster       K8s Cluster     K8s Cluster
   (Production)      (Staging)       (Multi-region)
```

---

## 🔑 Multi-Tenancy Strategy

### 1. Data Isolation

#### Neo4j: Database-per-Client
```cypher
// Create client database
CREATE DATABASE client1_kg;
CREATE DATABASE client2_kg;

// Switch to client database
:use client1_kg

// All queries are isolated
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
RETURN e, r
```

**Benefits**:
- ✅ Complete data isolation
- ✅ Easy to backup/restore per client
- ✅ Easy to migrate client to different server
- ✅ Clear billing (storage per database)

#### Kafka: Topic-per-Client
```
Topics:
- client1.events.normalized
- client1.logs.normalized
- client1.state.k8s.resource
- client1.state.k8s.topology

- client2.events.normalized
- client2.logs.normalized
...
```

**Benefits**:
- ✅ Logical separation
- ✅ Easy to scale (partitions per client)
- ✅ Clear billing (messages per topic)

---

### 2. Authentication & Authorization

#### API Key per Client
```bash
# Client gets API key from dashboard
API_KEY="client1_abc123def456"

# All API calls include key
curl -H "X-API-Key: ${API_KEY}" \
  https://api.kg-rca.your-company.com/api/v1/search/semantic \
  -d '{"query": "memory leak"}'
```

#### Kafka SASL Authentication
```yaml
# Client config
kafka:
  sasl:
    enabled: true
    mechanism: PLAIN
    username: "client1"
    password: "client1_kafka_password"
```

**Access Control**:
- Client1 can only read/write to `client1.*` topics
- Enforced via Kafka ACLs

---

### 3. Rate Limiting

#### Per-Plan Limits
```yaml
# Free tier
rateLimits:
  apiCalls: 100/minute
  rca: 10/hour
  events: 10000/day

# Basic tier ($99/month)
rateLimits:
  apiCalls: 1000/minute
  rca: 100/hour
  events: 100000/day

# Pro tier ($499/month)
rateLimits:
  apiCalls: 10000/minute
  rca: 1000/hour
  events: 1000000/day

# Enterprise tier (custom)
rateLimits:
  apiCalls: unlimited
  rca: unlimited
  events: unlimited
```

**Enforcement**: API Gateway (Kong) + Redis

---

## 💰 Billing Model

### Metrics Tracked per Client

```yaml
metrics:
  # Storage
  - neo4j_storage_gb
  - kafka_storage_gb

  # Compute
  - events_ingested_count
  - rca_queries_count
  - semantic_search_count
  - api_calls_count

  # Resources
  - graph_nodes_count
  - graph_edges_count
  - incidents_count
```

### Pricing Tiers

#### Free Tier
```
$0/month
- 10,000 events/day
- 10 RCA queries/hour
- 1 cluster
- 7 days retention
- Community support
```

#### Basic Tier
```
$99/month
- 100,000 events/day
- 100 RCA queries/hour
- 3 clusters
- 30 days retention
- Email support
```

#### Pro Tier
```
$499/month
- 1M events/day
- 1,000 RCA queries/hour
- 10 clusters
- 90 days retention
- Priority support
- Custom integrations
```

#### Enterprise Tier
```
Custom pricing
- Unlimited events
- Unlimited queries
- Unlimited clusters
- Custom retention
- Dedicated support
- On-premise option
- SLA guarantee
```

### Usage Calculation

```sql
-- Daily usage per client
SELECT
    client_id,
    SUM(CASE WHEN metric = 'events_ingested' THEN value ELSE 0 END) as events,
    SUM(CASE WHEN metric = 'rca_queries' THEN value ELSE 0 END) as rca_queries,
    SUM(CASE WHEN metric = 'storage_gb' THEN value ELSE 0 END) as storage_gb,
    DATE(timestamp) as date
FROM usage_metrics
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY client_id, DATE(timestamp);

-- Monthly invoice
SELECT
    c.name as client_name,
    c.plan,
    SUM(um.value) as total_events,
    ROUND(SUM(um.value) / 1000000 * 0.10, 2) as overage_charge
FROM clients c
JOIN usage_metrics um ON c.id = um.client_id
WHERE um.metric = 'events_ingested'
  AND um.timestamp >= DATE_FORMAT(NOW(), '%Y-%m-01')
  AND um.value > (
      SELECT plan_limit FROM plans WHERE name = c.plan
  )
GROUP BY c.id;
```

---

## 🚀 Deployment Process

### YOUR Server Deployment (One-Time)

```bash
# 1. Deploy YOUR infrastructure
cd production/helm-chart/server
helm install kg-rca-server ./kg-rca-server \
  --namespace kg-rca-server \
  --create-namespace \
  --values production-values.yaml

# 2. Verify all services are running
kubectl get pods -n kg-rca-server

# 3. Get external IPs/URLs
kubectl get ingress -n kg-rca-server

# 4. Set up DNS
api.kg-rca.your-company.com -> API Gateway IP
grafana.kg-rca.your-company.com -> Grafana IP
```

---

### Client Onboarding (Repeatable)

```bash
# 1. Create client in database
curl -X POST https://api.kg-rca.your-company.com/admin/clients \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -d '{
    "name": "Acme Corp",
    "plan": "pro",
    "contact_email": "admin@acme.com"
  }'

# Response:
{
  "client_id": "client-acme-abc123",
  "api_key": "acme_xyz789_secret",
  "kafka_username": "client-acme-abc123",
  "kafka_password": "kafka_pass_xyz"
}

# 2. Create Neo4j database for client
docker exec neo4j cypher-shell -u neo4j -p password \
  "CREATE DATABASE client_acme_abc123_kg"

# 3. Create Kafka ACLs for client
kafka-acls.sh --bootstrap-server localhost:9092 \
  --add --allow-principal User:client-acme-abc123 \
  --operation Write --topic "client-acme-abc123.*"

# 4. Send client their install package
cat > acme-values.yaml <<EOF
client:
  id: "client-acme-abc123"
  apiKey: "acme_xyz789_secret"
  serverUrl: "https://api.kg-rca.your-company.com"
  kafka:
    brokers: "kafka.kg-rca.your-company.com:9092"
    sasl:
      enabled: true
      username: "client-acme-abc123"
      password: "kafka_pass_xyz"
EOF

# 5. Client installs agents
helm install kg-rca-agent ./kg-rca-agent \
  --namespace observability \
  --values acme-values.yaml
```

---

## 🔒 Security

### TLS Everywhere
- Client → Your API: HTTPS (TLS 1.3)
- Client → Kafka: TLS + SASL
- Internal services: mTLS

### Authentication
- API Key for REST API
- SASL/PLAIN for Kafka (client-specific credentials)
- JWT for dashboard access

### Network Isolation
- Clients can ONLY access their own data
- Kafka ACLs enforce topic access
- Neo4j database isolation

### Data Encryption
- At rest: Encrypted volumes (AES-256)
- In transit: TLS 1.3
- Backups: Encrypted

---

## 📊 Monitoring YOUR Platform

### Key Metrics

```yaml
# Server health
- neo4j_up
- kafka_up
- graph_builder_up

# Per-client metrics
- client_events_per_second{client_id}
- client_rca_queries_per_minute{client_id}
- client_kafka_lag{client_id, topic}
- client_storage_gb{client_id}

# Billing metrics
- client_api_calls_total{client_id, plan}
- client_overage_events{client_id}

# Performance
- rca_query_latency_ms{percentile="p95"}
- semantic_search_latency_ms{percentile="p95"}
- kafka_consumer_lag{group="graph-builder"}
```

### Alerts

```yaml
alerts:
  - alert: ClientHighLag
    expr: client_kafka_lag{client_id} > 100000
    for: 10m
    annotations:
      summary: "Client {{ $labels.client_id }} has high lag"

  - alert: ClientOverage
    expr: client_events_per_day > client_plan_limit * 1.2
    annotations:
      summary: "Client {{ $labels.client_id }} exceeding plan by 20%"

  - alert: SystemHighLoad
    expr: rate(events_total[5m]) > 100000
    annotations:
      summary: "System processing >100k events/min"
```

---

## 🔄 Client Lifecycle

### Onboarding
1. Client signs up on website
2. You create client_id, API keys, Kafka credentials
3. You provision Neo4j database
4. Client installs Helm chart in their cluster
5. Agents start sending data
6. Client accesses dashboard

### Active Usage
1. Agents continuously send data to YOUR Kafka
2. Graph Builder processes and writes to client's Neo4j database
3. Client queries via YOUR API
4. Billing service tracks usage
5. Monthly invoice generated

### Offboarding
1. Client cancels subscription
2. Stop their Kafka ingestion
3. Export their data (optional)
4. Delete their Neo4j database after 30 days
5. Archive billing data

---

## 💡 Scaling Strategy

### Scale YOUR Infrastructure

#### Horizontal Scaling
```yaml
# Auto-scale based on load
graphBuilder:
  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 100
    targetCPUUtilizationPercentage: 70

kgApi:
  autoscaling:
    enabled: true
    minReplicas: 10
    maxReplicas: 50
```

#### Vertical Scaling
```yaml
# Increase resources as clients grow
neo4j:
  resources:
    requests:
      cpu: 16000m
      memory: 64Gi

kafka:
  resources:
    requests:
      cpu: 8000m
      memory: 32Gi
```

### Regional Deployment

```
US-EAST:   api-us-east.kg-rca.com
EU-WEST:   api-eu-west.kg-rca.com
AP-SOUTH:  api-ap-south.kg-rca.com

# Client connects to nearest region
client:
  serverUrl: "https://api-us-east.kg-rca.com"
```

---

## 📋 Client Installation Instructions

### Step 1: Get Credentials
```
Visit: https://dashboard.kg-rca.your-company.com
Navigate to: Settings → API Keys
Copy your:
- Client ID
- API Key
- Kafka credentials
```

### Step 2: Install Agent
```bash
# Download agent Helm chart
helm repo add kg-rca https://charts.kg-rca.your-company.com
helm repo update

# Create values file
cat > my-values.yaml <<EOF
client:
  id: "YOUR_CLIENT_ID"
  apiKey: "YOUR_API_KEY"
  serverUrl: "https://api.kg-rca.your-company.com"
  kafka:
    brokers: "kafka.kg-rca.your-company.com:9092"
    sasl:
      username: "YOUR_CLIENT_ID"
      password: "YOUR_KAFKA_PASSWORD"
EOF

# Install
helm install kg-rca-agent kg-rca/kg-rca-agent \
  --namespace observability \
  --create-namespace \
  --values my-values.yaml
```

### Step 3: Verify
```bash
# Check pods
kubectl get pods -n observability

# Check logs
kubectl logs -f deployment/kg-rca-state-watcher -n observability

# Verify data is flowing
curl -H "X-API-Key: YOUR_API_KEY" \
  https://api.kg-rca.your-company.com/api/v1/stats
```

---

## 🎯 Revenue Projections

### Example Calculation

```
Free tier:    1000 clients × $0 = $0
Basic tier:   500 clients × $99 = $49,500/month
Pro tier:     100 clients × $499 = $49,900/month
Enterprise:   10 clients × $5000 = $50,000/month

Total MRR: $149,400/month
Total ARR: $1,792,800/year
```

### Cost Structure

```
Infrastructure (AWS):
- EC2 instances: $5,000/month
- RDS (PostgreSQL): $1,000/month
- S3 (backups): $500/month
- CloudFront (CDN): $500/month
- Total: ~$7,000/month

Gross margin: ($149,400 - $7,000) / $149,400 = 95.3%
```

---

## 📖 Next Steps

1. **Deploy YOUR server**: See `SERVER_DEPLOYMENT.md`
2. **Onboard first client**: See `CLIENT_ONBOARDING.md`
3. **Set up billing**: See `BILLING_SETUP.md`
4. **Configure monitoring**: See `MONITORING.md`

---

**You're now ready to run a multi-tenant SaaS RCA platform!** 🚀
