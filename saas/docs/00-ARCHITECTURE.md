# Architecture Documentation

**Version**: 1.0.0
**Last Updated**: 2025-01-09
**Status**: Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Multi-Tenant Architecture](#multi-tenant-architecture)
3. [Component Descriptions](#component-descriptions)
4. [Data Flow](#data-flow)
5. [Security Architecture](#security-architecture)
6. [Scalability Design](#scalability-design)
7. [High Availability](#high-availability)
8. [Network Architecture](#network-architecture)
9. [Storage Architecture](#storage-architecture)
10. [Monitoring & Observability](#monitoring--observability)

---

## Overview

The KG RCA (Knowledge Graph Root Cause Analysis) platform is a **multi-tenant SaaS solution** that provides automated root cause analysis for Kubernetes incidents. The architecture separates **server infrastructure** (operated by the service provider) from **client agents** (deployed in customer clusters).

### Key Design Principles

- **Multi-Tenancy**: Complete data isolation using database-per-client and topic-per-client
- **Security First**: TLS everywhere, SASL authentication, API key validation
- **Scalability**: Horizontal and vertical scaling to support 100+ concurrent clients
- **Observability**: Comprehensive metrics, logs, and traces for operations
- **Reliability**: High availability, automated backups, disaster recovery

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    SERVER INFRASTRUCTURE                         │
│                    (Service Provider Hosted)                     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Ingress / Load Balancer                        │ │
│  │              (TLS Termination)                              │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                              │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │                   KG API Service                            │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │ Authentication Middleware                             │  │ │
│  │  │ - API Key Validation                                  │  │ │
│  │  │ - Rate Limiting (per plan)                            │  │ │
│  │  │ - Client ID Extraction                                │  │ │
│  │  └──────────────────────────────────────────────────────┘  │ │
│  │                                                              │ │
│  │  REST Endpoints (10-100 pods, auto-scaled):                │ │
│  │  - GET  /api/v1/search/semantic                            │ │
│  │  - GET  /api/v1/rca?incident_id={id}                       │ │
│  │  - POST /api/v1/query/cypher                               │ │
│  │  - GET  /api/v1/stats                                      │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                              │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │              Neo4j Cluster (3 nodes)                       │ │
│  │  Multi-Database Architecture:                              │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ client_acme_kg      (Acme Corp's graph)             │  │ │
│  │  │ client_beta_kg      (Beta Inc's graph)              │  │ │
│  │  │ client_gamma_kg     (Gamma LLC's graph)             │  │ │
│  │  │ ...                                                   │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │  Resources: 16-64 CPU, 64-256GB RAM, 500GB-10TB SSD      │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                              │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │                 Kafka Cluster (5 brokers)                  │ │
│  │  Multi-Topic Architecture:                                 │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ Client 1 Topics:                                     │  │ │
│  │  │  - client1.events.normalized                         │  │ │
│  │  │  - client1.logs.normalized                           │  │ │
│  │  │  - client1.state.k8s.resource                        │  │ │
│  │  │  - client1.state.k8s.topology                        │  │ │
│  │  │                                                       │  │ │
│  │  │ Client 2 Topics:                                     │  │ │
│  │  │  - client2.events.normalized                         │  │ │
│  │  │  - client2.logs.normalized                           │  │ │
│  │  │  - client2.state.k8s.resource                        │  │ │
│  │  │  ...                                                  │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │  Resources: 8 CPU, 32GB RAM, 1TB SSD per broker          │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                              │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │              Graph Builder Service                         │ │
│  │  (RCA Engine - 5-50 pods, auto-scaled)                    │ │
│  │                                                             │ │
│  │  For each message:                                         │ │
│  │  1. Consume from client-specific topic                    │ │
│  │  2. Extract client_id from topic name                     │ │
│  │  3. Switch to client's Neo4j database                     │ │
│  │  4. Process event and create RCA links                    │ │
│  │  5. Update graph with confidence scores                   │ │
│  │                                                             │ │
│  │  Resources: 2-4 CPU, 4-8GB RAM per pod                    │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                              │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │              Billing Service (3 pods)                      │ │
│  │  - Usage tracking per client                               │ │
│  │  - Stripe integration for payments                         │ │
│  │  - Invoice generation                                      │ │
│  │  - Metrics: events, queries, storage                      │ │
│  └────────────────┬───────────────────────────────────────────┘ │
│                   │                                              │
│  ┌────────────────┴───────────────────────────────────────────┐ │
│  │              PostgreSQL (Billing DB)                       │ │
│  │  Tables:                                                    │ │
│  │  - clients (id, name, email, plan, status)                │ │
│  │  - api_keys (client_id, key, created_at)                  │ │
│  │  - subscriptions (client_id, stripe_id, plan)             │ │
│  │  - usage_metrics (client_id, metric, value, timestamp)    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │         Monitoring Stack                                    │ │
│  │  - Prometheus (metrics collection)                         │ │
│  │  - Grafana (dashboards)                                    │ │
│  │  - AlertManager (alerting)                                 │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                            ▲
                            │ HTTPS (TLS 1.3) + Kafka (TLS + SASL)
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────┴────────┐  ┌───────┴────────┐  ┌──────┴────────┐
│   CLIENT 1     │  │   CLIENT 2     │  │   CLIENT 3    │
│  (Acme Corp)   │  │  (Beta Inc)    │  │ (Gamma LLC)   │
├────────────────┤  ├────────────────┤  ├───────────────┤
│ KG RCA Agents  │  │ KG RCA Agents  │  │ KG RCA Agents │
│                │  │                │  │               │
│ State Watcher  │  │ State Watcher  │  │ State Watcher │
│ Vector Logs    │  │ Vector Logs    │  │ Vector Logs   │
│ Event Exporter │  │ Event Exporter │  │ Event Exporter│
│ Alert Receiver │  │ Alert Receiver │  │ Alert Receiver│
│                │  │                │  │               │
│ Resources:     │  │ Resources:     │  │ Resources:    │
│ 1-2 CPU        │  │ 1-2 CPU        │  │ 1-2 CPU       │
│ 2-4 GB RAM     │  │ 2-4 GB RAM     │  │ 2-4 GB RAM    │
└────────────────┘  └────────────────┘  └───────────────┘
  K8s Production      K8s Staging        K8s Multi-Region
```

---

## Multi-Tenant Architecture

### Database-per-Client Strategy

**Neo4j Multi-Database** provides complete data isolation:

```cypher
-- Server creates database per client during onboarding
CREATE DATABASE client_acme_abc123_kg;
CREATE DATABASE client_beta_xyz789_kg;

-- Switch to client database for all operations
:use client_acme_abc123_kg

-- All queries are scoped to this database
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.namespace = 'production'
RETURN e, r
LIMIT 100
```

**Benefits**:
- Complete data isolation (no cross-tenant data leakage)
- Easy backup/restore per client
- Simple client migration (export database, import elsewhere)
- Clear billing (storage per database)
- Database-level performance tuning per client

**Database Naming Convention**:
```
Pattern: client_{sanitized_name}_{unique_id}_kg

Examples:
- client_acme_abc123_kg
- client_beta_xyz789_kg
- client_gamma_def456_kg
```

### Topic-per-Client Strategy

**Kafka Multi-Topic** provides logical separation:

```
Topic Naming Convention:
{client_id}.{data_type}.{stage}

Examples:
client-acme-abc123.events.normalized
client-acme-abc123.logs.normalized
client-acme-abc123.state.k8s.resource
client-acme-abc123.state.k8s.topology
client-acme-abc123.alerts.raw

client-beta-xyz789.events.normalized
client-beta-xyz789.logs.normalized
...
```

**Kafka ACLs** enforce access control:

```bash
# Client can only write to their topics
kafka-acls --add \
  --allow-principal User:client-acme-abc123 \
  --operation Write \
  --topic "client-acme-abc123.*"

# Server graph-builder can read all topics
kafka-acls --add \
  --allow-principal User:graph-builder \
  --operation Read \
  --topic "*"
```

**Benefits**:
- Logical separation with shared infrastructure
- Per-client partitioning for parallelism
- Easy monitoring (metrics per topic)
- Clear billing (messages per topic)
- Supports multi-region replication

### Client Isolation Matrix

| Aspect | Isolation Method | Enforcement |
|--------|------------------|-------------|
| **Neo4j Data** | Separate databases | Database-level ACLs |
| **Kafka Topics** | Topic prefix | Kafka ACLs (SASL) |
| **API Access** | API key validation | Application-level middleware |
| **Storage** | Separate volumes | K8s PVC per database |
| **Metrics** | Label-based | Prometheus labels (client_id) |
| **Logs** | Structured logging | Log fields (client_id) |
| **Billing** | Database tracking | PostgreSQL tables |

---

## Component Descriptions

### Neo4j (Graph Database)

**Purpose**: Stores the knowledge graph with temporal, causal, and structural relationships.

**Configuration**:
```yaml
neo4j:
  replicaCount: 3              # HA cluster
  resources:
    cpu: 16 cores
    memory: 64 GB
    storage: 500 GB SSD

  config:
    heap_size: 32 GB
    pagecache: 16 GB
    transaction_max: 8 GB

  plugins:
    - apoc                     # Graph algorithms
```

**Key Features**:
- Multi-database support (100+ databases)
- APOC plugin for graph algorithms
- Cluster mode with 3 replicas (HA)
- Automated backups (daily, 30-day retention)

**Performance**:
- Query latency: P95 < 100ms
- Write throughput: 10K ops/sec
- Storage efficiency: 1GB per 1M events (typical)

---

### Kafka (Event Stream)

**Purpose**: Message broker for ingesting client events, logs, and state.

**Configuration**:
```yaml
kafka:
  replicaCount: 5              # 5 brokers
  resources:
    cpu: 8 cores per broker
    memory: 32 GB per broker
    storage: 1 TB SSD per broker

  config:
    partitions: 6 per topic
    replication_factor: 3
    retention: 7 days
    compression: gzip
```

**SASL Authentication**:
```yaml
auth:
  mechanism: SCRAM-SHA-512
  client_credentials:
    - username: client-acme-abc123
      password: <generated>
    - username: client-beta-xyz789
      password: <generated>
```

**Performance**:
- Throughput: 100K messages/sec (peak)
- Latency: P95 < 10ms
- Consumer lag: Target < 1000 messages

---

### Graph Builder (RCA Engine)

**Purpose**: Consumes events from Kafka, processes them, and creates RCA links in Neo4j.

**Configuration**:
```yaml
graphBuilder:
  replicaCount: 5-50           # Auto-scaled
  resources:
    cpu: 2-4 cores per pod
    memory: 4-8 GB per pod

  autoscaling:
    minReplicas: 5
    maxReplicas: 50
    targetCPU: 70%
```

**Processing Pipeline**:
```
1. Consume message from Kafka
   ↓
2. Parse and validate message
   ↓
3. Extract client_id from topic name
   ↓
4. Switch to client's Neo4j database
   ↓
5. Create/update Resource nodes
   ↓
6. Create/update Episodic nodes
   ↓
7. Detect severity escalations
   ↓
8. Cluster incidents (SAME_INCIDENT edges)
   ↓
9. Compute RCA links (POTENTIAL_CAUSE edges)
   ↓
10. Calculate confidence scores
   ↓
11. Emit metrics to Prometheus
```

**RCA Algorithm**:
- **Temporal Window**: 15 minutes before incident
- **Distance-based Scoring**: Graph distance (1-3 hops)
- **Domain Correlation**: Resource types (pod → deployment → service)
- **Confidence Scoring**: 0.0 - 1.0 (composite score)

**Performance**:
- Message processing: P95 < 500ms
- RCA computation: P95 < 200ms
- Throughput: 1K events/sec per pod

---

### KG API (REST API)

**Purpose**: Provides HTTP REST API for querying the knowledge graph.

**Configuration**:
```yaml
kgApi:
  replicaCount: 10-100         # Auto-scaled
  resources:
    cpu: 1-2 cores per pod
    memory: 2-4 GB per pod

  autoscaling:
    minReplicas: 10
    maxReplicas: 100
    targetCPU: 70%
```

**Key Endpoints**:

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/api/v1/search/semantic` | GET | Semantic search in graph | API Key |
| `/api/v1/rca` | GET | Get RCA for incident | API Key |
| `/api/v1/query/cypher` | POST | Execute Cypher query | API Key |
| `/api/v1/stats` | GET | Client statistics | API Key |
| `/api/v1/incidents` | GET | List incidents | API Key |
| `/api/v1/resources` | GET | List resources | API Key |

**Authentication Flow**:
```
1. Client sends request with X-API-Key header
   ↓
2. API validates key against PostgreSQL
   ↓
3. Extract client_id from api_keys table
   ↓
4. Check rate limits (Redis)
   ↓
5. Switch to client's Neo4j database
   ↓
6. Execute query
   ↓
7. Return results
```

**Rate Limiting**:
```yaml
Free:       100 requests/minute
Basic:      1000 requests/minute
Pro:        10000 requests/minute
Enterprise: Unlimited
```

**Performance**:
- API latency: P95 < 100ms
- Throughput: 10K requests/sec (total)

---

### Billing Service

**Purpose**: Tracks usage metrics and manages Stripe subscriptions.

**Configuration**:
```yaml
billingService:
  replicaCount: 3
  resources:
    cpu: 500m
    memory: 1 GB
```

**Tracked Metrics**:
```sql
CREATE TABLE usage_metrics (
  id BIGSERIAL PRIMARY KEY,
  client_id VARCHAR(255) NOT NULL,
  metric VARCHAR(100) NOT NULL,
  value BIGINT NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  INDEX idx_client_metric_time (client_id, metric, timestamp)
);

Metrics:
- events_ingested_count
- rca_queries_count
- semantic_search_count
- api_calls_count
- storage_bytes
- graph_nodes_count
- graph_edges_count
```

**Stripe Integration**:
```go
// Monthly invoice calculation
invoice := stripe.Invoice{
  Customer: client.StripeID,
  Items: []{
    {
      Plan: client.Plan,
      Amount: planPrice,
    },
    {
      Description: "Overage: 500K events",
      Amount: 500000 * 0.0001, // $0.0001 per event
    },
  },
}
```

---

### PostgreSQL (Billing Database)

**Purpose**: Stores client metadata, API keys, and usage metrics.

**Schema**:
```sql
CREATE TABLE clients (
  id VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  plan VARCHAR(50) NOT NULL,  -- free, basic, pro, enterprise
  status VARCHAR(50) NOT NULL,  -- active, suspended, cancelled
  stripe_customer_id VARCHAR(255),
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE api_keys (
  id BIGSERIAL PRIMARY KEY,
  client_id VARCHAR(255) NOT NULL REFERENCES clients(id),
  key_hash VARCHAR(255) NOT NULL UNIQUE,
  key_prefix VARCHAR(20) NOT NULL,  -- For display (e.g., "kg_abc...")
  permissions JSONB,
  created_at TIMESTAMP NOT NULL,
  last_used_at TIMESTAMP
);

CREATE TABLE subscriptions (
  id BIGSERIAL PRIMARY KEY,
  client_id VARCHAR(255) NOT NULL REFERENCES clients(id),
  stripe_subscription_id VARCHAR(255) NOT NULL,
  plan VARCHAR(50) NOT NULL,
  status VARCHAR(50) NOT NULL,
  current_period_start TIMESTAMP NOT NULL,
  current_period_end TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL
);
```

---

### Prometheus (Metrics)

**Purpose**: Collects and stores time-series metrics from all components.

**Key Metrics**:

```yaml
# Server Health
- neo4j_up
- kafka_up
- graph_builder_up

# Message Processing
- kg_messages_processed_total{topic, status}
- kg_message_processing_duration_seconds{topic}

# RCA Quality
- kg_rca_links_created_total
- kg_rca_accuracy_at_k{k="1,3,5,10"}
- kg_rca_mean_average_rank
- kg_rca_confidence_score{score_type}

# Performance
- kg_processing_latency_p95_seconds{operation}
- kg_neo4j_query_duration_seconds{operation}
- kg_kafka_consumer_lag{topic, partition}

# Per-Client Metrics
- kg_client_events_sent_total{client_id}
- kg_client_storage_bytes{client_id}
- kg_client_api_calls_total{client_id}
```

---

### Grafana (Dashboards)

**Purpose**: Visualizes metrics and provides operational dashboards.

**Key Dashboards**:
1. **Server Overview**: Overall health, resource usage
2. **Per-Client Dashboard**: Client-specific metrics
3. **RCA Quality**: A@K accuracy, MAR, confidence scores
4. **Performance**: Latencies, throughput, SLA compliance
5. **Billing**: Usage trends, overage tracking

---

## Data Flow

### Event Ingestion Flow

```
┌─────────────────┐
│ Client Cluster  │
│                 │
│ [Pod Restart]   │  ← Something happens
└────────┬────────┘
         │
         │ 1. State Watcher detects pod state change
         ↓
┌─────────────────┐
│ State Watcher   │
│ (Client Agent)  │
└────────┬────────┘
         │
         │ 2. Serialize to JSON, send to Kafka
         ↓
┌─────────────────────────────────┐
│ Kafka Topic                     │
│ client-acme-abc123.state.k8s... │
└────────┬────────────────────────┘
         │
         │ 3. Graph Builder consumes
         ↓
┌─────────────────┐
│ Graph Builder   │
│ (Server)        │
│                 │
│ 1. Parse JSON   │
│ 2. Extract      │
│    client_id    │
│ 3. Switch DB    │
│    :use client_ │
│     acme_kg     │
└────────┬────────┘
         │
         │ 4. Upsert nodes and edges
         ↓
┌──────────────────────────────────┐
│ Neo4j Database                   │
│ client_acme_abc123_kg            │
│                                  │
│ CREATE (r:Resource {             │
│   name: "frontend-pod-abc",      │
│   namespace: "production",       │
│   kind: "Pod"                    │
│ })                               │
│                                  │
│ CREATE (e:Episodic {             │
│   severity: "error",             │
│   message: "CrashLoopBackOff",   │
│   timestamp: 1234567890          │
│ })                               │
│                                  │
│ CREATE (e)-[:ABOUT]->(r)         │
└──────────────────────────────────┘
```

### RCA Computation Flow

```
Trigger: New error event arrives

┌─────────────────────────────────────────────────────────┐
│ 1. Detect Incident (Severity = error/critical)          │
│    CREATE (inc:Incident {                               │
│      id: "inc-123",                                     │
│      severity: "error",                                 │
│      resource: "frontend-pod-abc",                      │
│      timestamp: 1234567890                              │
│    })                                                    │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Look back 15 minutes (RCA_WINDOW)                    │
│    MATCH (prior:Episodic)                               │
│    WHERE prior.timestamp >= incident.timestamp - 900    │
│      AND prior.timestamp < incident.timestamp           │
│    RETURN prior                                          │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│ 3. For each prior event, compute confidence score:      │
│                                                          │
│    score_temporal = 1.0 - (time_diff / 900)            │
│      (Earlier = higher score)                           │
│                                                          │
│    score_distance = 1.0 / (graph_distance + 1)         │
│      (Closer = higher score)                            │
│                                                          │
│    score_domain = domain_correlation(prior, incident)   │
│      (Same resource type = higher score)                │
│                                                          │
│    final_confidence =                                   │
│      0.4 * score_temporal +                             │
│      0.3 * score_distance +                             │
│      0.3 * score_domain                                 │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Create RCA links (top N=10 causes)                   │
│    CREATE (prior)-[:POTENTIAL_CAUSE {                   │
│      confidence: final_confidence,                      │
│      temporal_score: score_temporal,                    │
│      distance_score: score_distance,                    │
│      domain_score: score_domain,                        │
│      created_at: NOW()                                  │
│    }]->(incident)                                        │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Emit metrics                                          │
│    kg_rca_links_created_total++                         │
│    kg_rca_confidence_score.observe(final_confidence)    │
└─────────────────────────────────────────────────────────┘
```

### Query Flow (Client API Request)

```
┌────────────────┐
│ Client App     │
│ (DevOps Tool)  │
└────────┬───────┘
         │
         │ GET /api/v1/rca?incident_id=inc-123
         │ X-API-Key: kg_acme_xyz...
         ↓
┌──────────────────────────────────┐
│ Load Balancer / Ingress          │
│ (TLS Termination)                │
└────────┬─────────────────────────┘
         │
         ↓
┌──────────────────────────────────┐
│ KG API Pod                       │
│                                  │
│ 1. Validate API key              │
│    SELECT client_id              │
│    FROM api_keys                 │
│    WHERE key_hash = hash(key)    │
│                                  │
│    → client_id = "acme-abc123"   │
│                                  │
│ 2. Check rate limit (Redis)     │
│    INCR rate_limit:acme:minute   │
│    → 45 requests (under limit)   │
│                                  │
│ 3. Switch to client's database   │
│    USE client_acme_abc123_kg     │
└────────┬─────────────────────────┘
         │
         ↓
┌──────────────────────────────────────────────────┐
│ Neo4j Query                                      │
│                                                  │
│ MATCH (incident:Incident {id: "inc-123"})       │
│ MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]-     │
│       (incident)                                 │
│ RETURN cause, r                                  │
│ ORDER BY r.confidence DESC                       │
│ LIMIT 10                                         │
└────────┬─────────────────────────────────────────┘
         │
         ↓
┌──────────────────────────────────┐
│ Response                         │
│ {                                │
│   "incident_id": "inc-123",      │
│   "causes": [                    │
│     {                            │
│       "event_id": "evt-456",     │
│       "confidence": 0.92,        │
│       "message": "OOMKilled",    │
│       "resource": "backend-pod", │
│       "timestamp": 1234567800    │
│     },                           │
│     ...                          │
│   ]                              │
│ }                                │
└──────────────────────────────────┘
```

---

## Security Architecture

### Authentication Mechanisms

| Component | Method | Details |
|-----------|--------|---------|
| **API Access** | API Key | X-API-Key header, SHA-256 hash |
| **Kafka Access** | SASL/SCRAM-SHA-512 | Per-client credentials |
| **Neo4j Access** | Basic Auth | Internal only, not exposed |
| **Grafana** | Session-based | Admin console only |
| **PostgreSQL** | Password | Internal only, not exposed |

### API Key Format

```
Format: kg_{client_id}_{random_32_chars}

Examples:
kg_acme_abc123_9f4b2e8d1c7a6f3e5b8d2c1a9f4b
kg_beta_xyz789_1a2b3c4d5e6f7g8h9i0j1k2l3m4n

Storage:
- Store SHA-256 hash in PostgreSQL
- Display only first 12 chars in dashboard: "kg_acme_abc1..."
- Never log full API keys
```

### Kafka SASL Configuration

```yaml
# Server-side (Kafka)
listener.name.sasl_plaintext.scram-sha-512.sasl.jaas.config=\
  org.apache.kafka.common.security.scram.ScramLoginModule required;

# Client credentials (created per client)
kafka-configs --bootstrap-server kafka:9092 \
  --alter --add-config 'SCRAM-SHA-512=[password=client_password]' \
  --entity-type users --entity-name client-acme-abc123

# Client-side (Agent)
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule \
  required username="client-acme-abc123" password="client_password";
```

### TLS Configuration

```yaml
# Ingress (API Gateway)
tls:
  - secretName: kg-api-tls
    hosts:
      - api.kg-rca.yourcompany.com

# Certificate Manager
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: kg-api-tls
spec:
  secretName: kg-api-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - api.kg-rca.yourcompany.com

# Kafka TLS (optional, for production)
listeners:
  - SSL://kafka:9093
ssl.keystore.location=/var/private/ssl/kafka.keystore.jks
ssl.keystore.password=changeme
ssl.key.password=changeme
```

### Network Policies

```yaml
# Restrict API pod egress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kg-api-netpol
spec:
  podSelector:
    matchLabels:
      app: kg-api
  egress:
    - to:
      - podSelector:
          matchLabels:
            app: neo4j
      ports:
      - protocol: TCP
        port: 7687
    - to:
      - podSelector:
          matchLabels:
            app: postgresql
      ports:
      - protocol: TCP
        port: 5432

# Restrict Graph Builder egress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: graph-builder-netpol
spec:
  podSelector:
    matchLabels:
      app: graph-builder
  egress:
    - to:
      - podSelector:
          matchLabels:
            app: kafka
      ports:
      - protocol: TCP
        port: 9092
    - to:
      - podSelector:
          matchLabels:
            app: neo4j
      ports:
      - protocol: TCP
        port: 7687
```

### Secrets Management

```yaml
# Kubernetes Secrets
apiVersion: v1
kind: Secret
metadata:
  name: neo4j-auth
type: Opaque
stringData:
  username: neo4j
  password: <generated-password>

---
apiVersion: v1
kind: Secret
metadata:
  name: stripe-api-key
type: Opaque
stringData:
  api_key: <stripe-secret-key>

# External Secrets Operator (recommended for production)
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: neo4j-auth
spec:
  secretStoreRef:
    name: aws-secrets-manager
  target:
    name: neo4j-auth
  data:
    - secretKey: password
      remoteRef:
        key: prod/neo4j/password
```

---

## Scalability Design

### Horizontal Scaling

**Auto-scaling Configuration**:

```yaml
# Graph Builder HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: graph-builder-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: graph-builder
  minReplicas: 5
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    - type: Pods
      pods:
        metric:
          name: kafka_consumer_lag
        target:
          type: AverageValue
          averageValue: "1000"

# KG API HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kg-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kg-api
  minReplicas: 10
  maxReplicas: 100
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

**Scaling Triggers**:
- CPU > 70% → Scale up
- Memory > 80% → Scale up
- Kafka lag > 1000 messages → Scale up Graph Builder
- API latency P95 > 200ms → Scale up KG API

### Vertical Scaling

**Resource Progression**:

```yaml
# Small deployment (10 clients)
neo4j:
  resources:
    cpu: 8 cores
    memory: 32 GB
    storage: 500 GB

kafka:
  resources:
    cpu: 4 cores per broker
    memory: 16 GB per broker
    storage: 500 GB per broker

# Medium deployment (50 clients)
neo4j:
  resources:
    cpu: 16 cores
    memory: 64 GB
    storage: 2 TB

kafka:
  resources:
    cpu: 8 cores per broker
    memory: 32 GB per broker
    storage: 1 TB per broker

# Large deployment (200+ clients)
neo4j:
  resources:
    cpu: 32 cores
    memory: 256 GB
    storage: 10 TB

kafka:
  resources:
    cpu: 16 cores per broker
    memory: 64 GB per broker
    storage: 2 TB per broker
```

### Database Scaling

**Neo4j Cluster Expansion**:

```bash
# Start with 3-node cluster
neo4j:
  replicaCount: 3

# Expand to 5 nodes for higher availability
neo4j:
  replicaCount: 5

# Scale storage independently
neo4j:
  persistence:
    size: 500Gi  # → 2Ti → 10Ti
```

**Database Sharding** (if needed for 500+ clients):

```
Shard by client_id hash:
- Shard 1: clients with hash(id) % 3 == 0
- Shard 2: clients with hash(id) % 3 == 1
- Shard 3: clients with hash(id) % 3 == 2

Each shard is a separate Neo4j cluster.
```

### Kafka Scaling

**Add Brokers**:

```bash
# Scale from 5 to 10 brokers
kubectl scale statefulset kafka --replicas=10 -n kg-rca-server

# Rebalance partitions
kafka-reassign-partitions.sh --bootstrap-server kafka:9092 \
  --reassignment-json-file expand.json --execute
```

**Increase Partitions**:

```bash
# Increase partitions from 6 to 12 for high-volume clients
kafka-topics.sh --bootstrap-server kafka:9092 \
  --alter --topic client-acme-abc123.events.normalized \
  --partitions 12
```

---

## High Availability

### Component HA Configuration

| Component | Replicas | Strategy | Recovery Time |
|-----------|----------|----------|---------------|
| **Neo4j** | 3 nodes | Cluster with leader election | < 30s |
| **Kafka** | 5 brokers | Replication factor 3 | < 10s |
| **Graph Builder** | 5-50 pods | StatelessSet, rolling update | < 5s |
| **KG API** | 10-100 pods | StatelessSet, rolling update | < 5s |
| **PostgreSQL** | 1 primary + 2 replicas | Streaming replication | < 60s |
| **Zookeeper** | 3 nodes | Ensemble | < 30s |

### Data Replication

**Neo4j Cluster**:
```
┌────────────┐     ┌────────────┐     ┌────────────┐
│  Neo4j-0   │────▶│  Neo4j-1   │────▶│  Neo4j-2   │
│  (Leader)  │     │ (Follower) │     │ (Follower) │
└────────────┘     └────────────┘     └────────────┘
     │                   │                   │
     └───────────────────┴───────────────────┘
              Raft consensus protocol

Write: Leader only
Read: Any node (eventual consistency)
Failover: Automatic leader election (< 30s)
```

**Kafka Replication**:
```
Topic: client-acme-abc123.events.normalized
Partitions: 6
Replication Factor: 3

Partition 0: [Broker-1 (leader), Broker-2, Broker-3]
Partition 1: [Broker-2 (leader), Broker-3, Broker-4]
...

ISR (In-Sync Replicas): min 2 required
Unclean leader election: Disabled (prevent data loss)
```

### Disaster Recovery

**Backup Strategy**:

```yaml
# Neo4j Backups
backup:
  enabled: true
  schedule: "0 2 * * *"  # Daily at 2 AM
  retention: 30 days
  storage:
    type: s3
    bucket: kg-rca-backups
    path: neo4j/{client_id}/{date}

# PostgreSQL Backups
pgBackRest:
  schedule: "0 3 * * *"  # Daily at 3 AM
  retention: 30 days
  type: full
  differential: daily

# Kafka Topic Backups (MirrorMaker)
mirrorMaker:
  enabled: true
  destination: s3://kg-rca-backups/kafka
  schedule: "0 4 * * *"
```

**Recovery Procedures**:

```bash
# Restore Neo4j database
neo4j-admin restore \
  --from=/backups/client_acme_abc123_kg/2025-01-08 \
  --database=client_acme_abc123_kg

# Restore PostgreSQL
pgbackrest restore \
  --stanza=billing \
  --type=time \
  --target="2025-01-08 02:00:00"

# Restore Kafka topics
kafka-mirror-maker \
  --consumer.config mirror-consumer.properties \
  --producer.config mirror-producer.properties \
  --whitelist="client-acme-abc123.*"
```

**RTO/RPO Targets**:

| Scenario | RTO | RPO | Recovery Method |
|----------|-----|-----|-----------------|
| **Pod failure** | < 5s | 0 | K8s auto-restart |
| **Node failure** | < 30s | 0 | K8s reschedule |
| **Database corruption** | < 1h | < 24h | Restore from backup |
| **Complete region failure** | < 4h | < 24h | Multi-region failover |
| **Accidental deletion** | < 2h | < 24h | Restore specific database |

---

## Network Architecture

### External Connectivity

```
Internet
   │
   ↓
┌────────────────────────────┐
│ Cloud Load Balancer        │
│ (TLS Termination)          │
│ - api.kg-rca.com           │
│ - grafana.kg-rca.com       │
└────────────┬───────────────┘
             │
             ↓
┌────────────────────────────┐
│ Ingress Controller         │
│ (nginx-ingress)            │
│ - Rate limiting            │
│ - WAF rules                │
└────────────┬───────────────┘
             │
      ┌──────┴──────┐
      ↓             ↓
┌──────────┐  ┌──────────┐
│ KG API   │  │ Grafana  │
│ Service  │  │ Service  │
└──────────┘  └──────────┘
```

### Internal Connectivity

```
┌────────────────────────────────────────────┐
│ Kubernetes Cluster (Private VPC)          │
│                                            │
│  ┌───────────┐    ┌───────────┐          │
│  │ KG API    │───▶│ Neo4j     │          │
│  │ (ClusterIP│    │ (Headless)│          │
│  │ Service)  │    │ Service)  │          │
│  └─────┬─────┘    └───────────┘          │
│        │                                   │
│        │          ┌───────────┐          │
│        └─────────▶│ PostgreSQL│          │
│                   │ (ClusterIP│          │
│                   │ Service)  │          │
│                   └───────────┘          │
│                                            │
│  ┌───────────┐    ┌───────────┐          │
│  │ Graph     │───▶│ Kafka     │          │
│  │ Builder   │    │ (Headless)│          │
│  │ (no svc)  │    │ Service)  │          │
│  └───────────┘    └─────┬─────┘          │
│        │                │                 │
│        └────────────────┘                 │
│                                            │
└────────────────────────────────────────────┘
              ▲
              │ TLS + SASL
┌─────────────┴────────────┐
│ Client Clusters          │
│ (Customer Networks)      │
└──────────────────────────┘
```

### Service Types

```yaml
# External services (exposed to internet)
kgApi:
  service:
    type: ClusterIP  # Behind Ingress
  ingress:
    enabled: true
    host: api.kg-rca.com

kafka:
  service:
    type: LoadBalancer  # Exposed to client clusters
    externalTrafficPolicy: Local

# Internal services (cluster-only)
neo4j:
  service:
    type: ClusterIP

postgresql:
  service:
    type: ClusterIP

graphBuilder:
  service:
    type: ClusterIP  # Metrics only
```

---

## Storage Architecture

### Persistent Volume Claims

```yaml
# Neo4j storage
neo4j:
  persistence:
    enabled: true
    storageClassName: fast-ssd  # AWS: gp3, GCP: pd-ssd, Azure: Premium_LRS
    size: 500Gi
    accessMode: ReadWriteOnce

# Kafka storage
kafka:
  persistence:
    enabled: true
    storageClassName: fast-ssd
    size: 1Ti per broker
    accessMode: ReadWriteOnce

# PostgreSQL storage
postgresql:
  persistence:
    enabled: true
    storageClassName: standard-ssd
    size: 100Gi
    accessMode: ReadWriteOnce

# Prometheus storage
prometheus:
  persistence:
    enabled: true
    storageClassName: standard-ssd
    size: 500Gi
    accessMode: ReadWriteOnce
```

### Storage Classes

```yaml
# Fast SSD (for databases)
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

# Standard SSD (for metrics)
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: standard-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
reclaimPolicy: Retain
```

### Storage Capacity Planning

| Client Count | Neo4j Storage | Kafka Storage | Total Storage |
|--------------|---------------|---------------|---------------|
| **10 clients** | 50 GB | 100 GB | 150 GB |
| **50 clients** | 250 GB | 500 GB | 750 GB |
| **100 clients** | 500 GB | 1 TB | 1.5 TB |
| **500 clients** | 2.5 TB | 5 TB | 7.5 TB |

**Per-Client Storage Estimate**:
- Events: 1 GB per 1M events
- Typical client: 100K events/day = 3 GB/month
- With 30-day retention: 3 GB × 30 = 90 GB per client

---

## Monitoring & Observability

### Metrics Collection

```yaml
# Prometheus scrape config
scrape_configs:
  - job_name: 'graph-builder'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names: [kg-rca-server]
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: graph-builder
        action: keep
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
    scrape_interval: 15s

  - job_name: 'kg-api'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names: [kg-rca-server]
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: kg-api
        action: keep
    scrape_interval: 15s

  - job_name: 'neo4j'
    static_configs:
      - targets: ['neo4j-0:7474', 'neo4j-1:7474', 'neo4j-2:7474']

  - job_name: 'kafka'
    static_configs:
      - targets: ['kafka-0:9092', 'kafka-1:9092', 'kafka-2:9092']
    metrics_path: /metrics
```

### Key Dashboards

**1. Server Overview Dashboard**:
- Total clients active
- Total events processed (last 24h)
- RCA accuracy (A@3)
- System resource utilization
- Error rate (last 1h)

**2. Per-Client Dashboard**:
- Events ingested (time series)
- RCA queries executed
- Storage usage (GB)
- API calls (with rate limit)
- Kafka lag per topic

**3. RCA Quality Dashboard**:
- Accuracy at K (A@1, A@3, A@5, A@10)
- Mean Average Rank (MAR)
- Confidence score distribution
- Null confidence link count
- RCA compute time (P50, P95, P99)

**4. Performance Dashboard**:
- Message processing latency (P50, P95, P99)
- Neo4j query duration
- API latency (P50, P95, P99)
- Kafka consumer lag
- End-to-end latency

### Alerting Rules

```yaml
groups:
  - name: server-health
    rules:
      - alert: Neo4jDown
        expr: neo4j_up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Neo4j instance is down"

      - alert: KafkaBrokerDown
        expr: kafka_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Kafka broker is down"

      - alert: HighConsumerLag
        expr: kg_kafka_consumer_lag > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High Kafka consumer lag: {{ $value }} messages"

      - alert: LowRCAAccuracy
        expr: kg_rca_accuracy_at_k{k="3"} < 0.85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "RCA accuracy below threshold: {{ $value }}"

      - alert: HighAPILatency
        expr: kg_processing_latency_p95_seconds{operation="api"} > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API P95 latency above 200ms: {{ $value }}s"
```

---

## Conclusion

This architecture provides:

- **Complete multi-tenancy** with database and topic isolation
- **Scalability** to support 100+ clients with auto-scaling
- **Security** with TLS, SASL, API keys, and network policies
- **High availability** with 3-node Neo4j cluster and 5-broker Kafka
- **Observability** with comprehensive metrics and dashboards
- **Disaster recovery** with automated backups and failover

**Next Steps**:
- [Server Deployment Guide](01-SERVER-DEPLOYMENT.md) - Deploy the server infrastructure
- [Client Onboarding Guide](02-CLIENT-ONBOARDING.md) - Onboard your first client
- [Operations Guide](03-OPERATIONS.md) - Day-to-day operations

---

**Document Version**: 1.0.0
**Maintained By**: Platform Engineering Team
**Last Review**: 2025-01-09
