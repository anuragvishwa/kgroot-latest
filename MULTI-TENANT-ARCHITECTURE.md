# Multi-Tenant Architecture - Knowledge Graph RCA Agent

## Overview

The KG RCA Agent supports multiple Kubernetes clusters (tenants) sending observability data to a single centralized Kafka/Neo4j infrastructure. This document explains how tenant isolation works and where the `client_id` comes from.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Kubernetes Cluster 1 (af-10)                                │
│  ├── Event-Exporter ─┐                                      │
│  ├── State-Watcher ──┤                                      │
│  ├── Vector ─────────┤                                      │
│  └── Alert-Receiver ─┘                                      │
└────────────────────────┼────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────────┐
│ Kubernetes Cluster 2 (af-11)                                │
│  ├── Event-Exporter ─┐                                      │
│  ├── State-Watcher ──┤                                      │
│  ├── Vector ─────────┤                                      │
│  └── Alert-Receiver ─┘                                      │
└────────────────────────┼────────────────────────────────────┘
                         │
                         ↓
              ┌─────────────────────┐
              │   Kafka Cluster     │
              │  (Shared Topics)    │
              │                     │
              │ events.normalized   │
              │ logs.normalized     │
              │ state.k8s.resource  │
              │ alerts.raw          │
              └──────────┬──────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ↓                               ↓
┌─────────────────────┐     ┌─────────────────────┐
│ Graph-Builder-af-10 │     │ Graph-Builder-af-11 │
│ CLIENT_ID=af-10     │     │ CLIENT_ID=af-11     │
└──────────┬──────────┘     └──────────┬──────────┘
           │                           │
           └───────────┬───────────────┘
                       ↓
              ┌─────────────────┐
              │   Neo4j Graph   │
              │                 │
              │ (:Resource)     │
              │ (:Episodic)     │
              │ (:Incident)     │
              │                 │
              │ All nodes have  │
              │ client_id field │
              └─────────────────┘
```

---

## How client_id Works

### 1. Client-Side Configuration (Kubernetes)

When installing the Helm chart, you specify a unique `client.id` for each cluster:

```bash
# Cluster 1 (Production US-East)
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --set client.id="af-10" \
  --set client.kafka.brokers="kafka.company.com:9092"

# Cluster 2 (Production EU-West)
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --set client.id="af-11" \
  --set client.kafka.brokers="kafka.company.com:9092"

# Cluster 3 (Staging)
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --set client.id="af-12" \
  --set client.kafka.brokers="kafka.company.com:9092"
```

**Where does client_id come from?**
- **You choose it!** It's a unique identifier you assign to each cluster
- Common patterns:
  - `af-10`, `af-11`, `af-12` (auto-incrementing)
  - `prod-us-east`, `prod-eu-west`, `staging`
  - `customer-acme-prod`, `customer-acme-dev`
  - `cluster-abc123` (random/hash)

**Requirements:**
- Must be unique across all clusters
- Only letters, numbers, hyphens, underscores
- Should be descriptive for easy identification

### 2. What Happens in Kubernetes

The `client.id` is stored in a ConfigMap and used by components:

```yaml
# ConfigMap created by Helm
apiVersion: v1
kind: ConfigMap
metadata:
  name: kg-rca-agent-config
data:
  CLIENT_ID: "af-10"  # ← Your chosen client_id
```

**Important:** The client_id is NOT added to Kafka messages by the Kubernetes components!

- ❌ Event-Exporter: Sends clean events without client_id
- ❌ State-Watcher: Sends resources without client_id
- ❌ Vector: Sends logs without client_id
- ❌ Alert-Receiver: Sends alerts without client_id

**Why?** This keeps Kafka topics clean with raw Kubernetes data, avoiding complex templating issues.

### 3. Server-Side Configuration (Graph-Builder)

On the central server (mini-server), you run one graph-builder instance per cluster:

```yaml
# docker-compose.yml on mini-server
version: '3.8'

services:
  # Graph-Builder for Cluster af-10
  kg-graph-builder-af-10:
    image: anuragvishwa/kg-graph-builder:1.0.20
    environment:
      CLIENT_ID: "af-10"  # ← Matches Helm chart client.id
      KAFKA_BROKERS: "kafka:9092"
      KAFKA_GROUP: "kg-builder-af-10"
      NEO4J_URI: "neo4j://neo4j:7687"
      NEO4J_USER: "neo4j"
      NEO4J_PASS: "password"

  # Graph-Builder for Cluster af-11
  kg-graph-builder-af-11:
    image: anuragvishwa/kg-graph-builder:1.0.20
    environment:
      CLIENT_ID: "af-11"  # ← Matches Helm chart client.id
      KAFKA_BROKERS: "kafka:9092"
      KAFKA_GROUP: "kg-builder-af-11"
      NEO4J_URI: "neo4j://neo4j:7687"
      NEO4J_USER: "neo4j"
      NEO4J_PASS: "password"

  # Graph-Builder for Cluster af-12
  kg-graph-builder-af-12:
    image: anuragvishwa/kg-graph-builder:1.0.20
    environment:
      CLIENT_ID: "af-12"  # ← Matches Helm chart client.id
      KAFKA_BROKERS: "kafka:9092"
      KAFKA_GROUP: "kg-builder-af-12"
      NEO4J_URI: "neo4j://neo4j:7687"
      NEO4J_USER: "neo4j"
      NEO4J_PASS: "password"
```

### 4. Graph-Builder Adds client_id

When graph-builder consumes messages from Kafka, it automatically adds the client_id:

```go
// From kg/graph-builder.go:1056-1065

// Fill client_id from payload or Kafka key or consumer default
if ev.ClientID == "" {
    ev.ClientID = raw.ClientID  // Try to get from JSON body
}
if ev.ClientID == "" && tenantFromKey != "" {
    ev.ClientID = tenantFromKey  // Try to get from Kafka key prefix
}
if ev.ClientID == "" && h.clientID != "" {
    ev.ClientID = h.clientID  // Use graph-builder's CLIENT_ID env var
}
```

**Fallback Order:**
1. Check if message has `client_id` field in JSON
2. Check if Kafka message key has `client_id::` prefix
3. **Use graph-builder's CLIENT_ID environment variable** ✅ (Most common)

### 5. Storage in Neo4j

All nodes in Neo4j get the `client_id` property:

```cypher
// Resources
CREATE (r:Resource:Pod {
  rid: "pod_uid_123",
  client_id: "af-10",  # ← Added by graph-builder
  name: "nginx-pod",
  namespace: "production"
})

// Events
CREATE (e:Episodic {
  eid: "event_uid_456",
  client_id: "af-10",  # ← Added by graph-builder
  reason: "Pulled",
  message: "Successfully pulled image"
})

// Incidents
CREATE (i:Incident {
  iid: "incident_789",
  client_id: "af-10",  # ← Added by graph-builder
  severity: "CRITICAL",
  summary: "Pod OOMKilled"
})
```

---

## Data Flow Example

### Example: Kubernetes Event

**Step 1: Kubernetes generates event**
```json
{
  "metadata": {
    "name": "nginx-pod.abc123",
    "namespace": "production"
  },
  "reason": "Pulled",
  "message": "Successfully pulled image nginx:1.21"
}
```

**Step 2: Event-Exporter sends to Kafka**
```json
Topic: events.normalized
Key: "abc123"
Value: {
  "metadata": {...},
  "reason": "Pulled",
  "message": "Successfully pulled image nginx:1.21"
}
// Note: NO client_id field!
```

**Step 3: Graph-Builder (CLIENT_ID=af-10) consumes**
```go
// Detects event.ClientID is empty
// Adds: event.ClientID = "af-10" (from env var)
```

**Step 4: Stored in Neo4j**
```cypher
CREATE (e:Episodic {
  eid: "abc123",
  client_id: "af-10",  # ← Added by graph-builder!
  reason: "Pulled",
  message: "Successfully pulled image nginx:1.21"
})
```

---

## Querying Multi-Tenant Data

### Query Specific Cluster

```cypher
// Get all events from cluster af-10
MATCH (e:Episodic {client_id: "af-10"})
RETURN e.reason, e.message, e.event_time
ORDER BY e.event_time DESC
LIMIT 10

// Get all resources from cluster af-11
MATCH (r:Resource {client_id: "af-11"})
RETURN r.kind, r.name, r.namespace

// Get incidents from cluster af-12
MATCH (i:Incident {client_id: "af-12"})
RETURN i.severity, i.summary, i.started_at
```

### Query All Clusters

```cypher
// Count events per cluster
MATCH (e:Episodic)
RETURN e.client_id, count(e) as event_count
ORDER BY event_count DESC

// Get critical incidents across all clusters
MATCH (i:Incident)
WHERE i.severity = "CRITICAL"
RETURN i.client_id, i.summary, i.started_at
ORDER BY i.started_at DESC
```

### Tenant Isolation

Neo4j indexes ensure fast filtering by client_id:

```cypher
// Indexes created by graph-builder
CREATE INDEX res_client_id FOR (r:Resource) ON (r.client_id)
CREATE INDEX epi_client_id FOR (e:Episodic) ON (e.client_id)
CREATE INDEX inc_client_id FOR (i:Incident) ON (i.client_id)
```

---

## Configuration Summary

### Client-Side (Kubernetes Cluster)

| Component | Uses client_id? | How? |
|-----------|----------------|------|
| Event-Exporter | ❌ No | Sends raw events |
| State-Watcher | ❌ No | Sends raw resources |
| Vector | ❌ No | Sends raw logs |
| Alert-Receiver | ❌ No | Sends raw alerts |

**Configuration:**
```bash
helm install kg-rca-agent anuragvishwa/kg-rca-agent \
  --set client.id="YOUR_UNIQUE_ID"  # ← Only place you set it on client side
```

### Server-Side (Mini-Server)

| Component | Uses client_id? | How? |
|-----------|----------------|------|
| Kafka | ❌ No | Stores raw messages |
| Graph-Builder | ✅ Yes | Adds client_id from CLIENT_ID env var |
| Neo4j | ✅ Yes | Stores all nodes with client_id |

**Configuration:**
```yaml
# docker-compose.yml
kg-graph-builder-af-10:
  environment:
    CLIENT_ID: "af-10"  # ← Must match Helm chart client.id
```

---

## Best Practices

### 1. Naming Convention

Choose a consistent naming scheme:

**By Environment + Region:**
```
prod-us-east-1
prod-eu-west-1
staging-us-east-1
dev-local
```

**By Customer + Environment:**
```
acme-prod
acme-staging
globex-prod
initech-prod
```

**By Simple ID:**
```
af-10, af-11, af-12, ...  # Simple incrementing
```

### 2. Documentation

Maintain a mapping file:

```yaml
# clusters.yaml
clusters:
  - id: af-10
    name: Production US-East
    region: us-east-1
    environment: production

  - id: af-11
    name: Production EU-West
    region: eu-west-1
    environment: production

  - id: af-12
    name: Staging US-East
    region: us-east-1
    environment: staging
```

### 3. Graph-Builder Deployment

Always ensure:
- One graph-builder per cluster
- CLIENT_ID matches Helm chart client.id exactly
- Unique KAFKA_GROUP per graph-builder

```yaml
# Good ✅
kg-graph-builder-af-10:
  environment:
    CLIENT_ID: "af-10"
    KAFKA_GROUP: "kg-builder-af-10"

# Bad ❌ - Reusing same CLIENT_ID
kg-graph-builder-af-10:
  environment:
    CLIENT_ID: "af-10"
kg-graph-builder-af-11:
  environment:
    CLIENT_ID: "af-10"  # ← Wrong! Should be "af-11"
```

---

## Troubleshooting

### Events Missing client_id in Neo4j

**Symptom:** Events stored with empty client_id

**Cause:** Graph-builder not configured with CLIENT_ID

**Fix:**
```bash
# Check graph-builder environment
docker inspect kg-graph-builder | grep CLIENT_ID

# Should show:
"CLIENT_ID=af-10"

# If missing, restart with CLIENT_ID:
docker run -d \
  --name kg-graph-builder \
  -e CLIENT_ID=af-10 \
  -e KAFKA_BROKERS=kafka:9092 \
  ... \
  anuragvishwa/kg-graph-builder:1.0.20
```

### Events from Multiple Clusters Mixed

**Symptom:** All events have same client_id even from different clusters

**Cause:** All graph-builders using same CLIENT_ID

**Fix:** Use unique CLIENT_ID for each graph-builder instance

### No Events in Neo4j

**Symptom:** Events in Kafka but not in Neo4j

**Cause:** Graph-builder not running or not consuming

**Check:**
```bash
# Check graph-builder is running
docker ps | grep graph-builder

# Check logs
docker logs kg-graph-builder

# Should see:
# single-tenant mode: client_id=af-10, consumer_group=kg-builder-af-10
# consuming topics: [events.normalized logs.normalized ...]
```

---

## Version History

### v1.0.47 (Current)
- ✅ Events sent without client_id in JSON body
- ✅ Graph-builder adds client_id from CLIENT_ID env var
- ✅ Multi-tenant support via graph-builder fallback
- ✅ Clean Kafka messages without template complexity

### Previous Versions (v1.0.40-1.0.46)
- ❌ Attempted to add client_id via event-exporter layout
- ❌ YAML parsing errors
- ❌ Double-encoding issues
- ❌ Overly complex templates

---

## Summary

**Client ID Flow:**

1. **You choose** a unique client_id for each cluster (e.g., `af-10`)
2. **Helm chart** stores it in ConfigMap but doesn't add it to messages
3. **Kubernetes components** send clean raw data to Kafka (no client_id)
4. **Graph-builder** (on server) reads CLIENT_ID from env var
5. **Graph-builder** adds client_id to all events/resources when storing
6. **Neo4j** stores everything with proper tenant isolation

**Key Insight:** The client_id is NOT in Kafka messages - it's added by graph-builder on the server side. This keeps Kafka topics clean and puts tenant management where it belongs: at the data processing layer.

---

## Related Documentation

- [INSTALLATION.md](INSTALLATION.md) - Installation guide
- [kg/graph-builder.go:1056-1065](kg/graph-builder.go#L1056-L1065) - client_id fallback logic
- [client-light/helm-chart/values.yaml:8](client-light/helm-chart/values.yaml#L8) - client.id configuration

---

## License

Apache 2.0