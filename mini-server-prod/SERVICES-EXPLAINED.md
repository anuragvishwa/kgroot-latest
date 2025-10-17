# Knowledge Graph Services Explained

## Overview

Your knowledge graph system has **10 different services** running. Here's what each one does and whether it's affected by multi-tenant setup.

## Infrastructure Services (Shared - Never Duplicated)

### 1. **Zookeeper** (`kg-zookeeper`)
- **What it does:** Coordinates Kafka cluster, manages broker metadata
- **Port:** 2181
- **Multi-tenant impact:** ❌ No change - shared by all clients
- **When to restart:** Only if Kafka has issues

### 2. **Kafka** (`kg-kafka`)
- **What it does:** Message broker that stores all logs, events, and state data
- **Port:** 9092 (external)
- **Topics:** `logs.normalized`, `events.normalized`, `state.k8s.resource`, `state.k8s.topology`, etc.
- **Multi-tenant impact:** ❌ No change - all clients write to same topics
- **When to restart:** Rarely - causes data ingestion pause

### 3. **Neo4j** (`kg-neo4j`)
- **What it does:** Graph database storing all resources, relationships, and incidents
- **Ports:** 7474 (HTTP), 7687 (Bolt)
- **Multi-tenant impact:** ❌ No change - shared database with `client_id` property
- **When to restart:** Only for upgrades or issues

### 4. **Kafka UI** (`kg-kafka-ui`)
- **What it does:** Web interface to view Kafka topics, messages, and consumer groups
- **Port:** 7777
- **Access:** http://localhost:7777
- **Multi-tenant impact:** ❌ No change - useful for monitoring all clients

## Processing Services (Multi-Tenant Aware)

### 5. **Alerts Enricher** (`kg-alerts-enricher`)
- **What it does:**
  - Reads raw events from `events.normalized` topic
  - Enriches them with current state information (pod status, node info, etc.)
  - Writes enriched alerts to `alerts.enriched` topic
- **Consumer group:** `alerts-enricher`
- **Multi-tenant impact:** ⚠️ **Should be multi-tenant aware but currently isn't**
- **Current behavior:** Processes all clients' events together
- **Recommendation:** Could add CLIENT_ID filtering if needed per client

### 6. **Graph Builder** (`kg-graph-builder` or `kg-graph-builder-client-*`)
- **What it does:**
  - Consumes from Kafka topics (logs, events, state)
  - Builds knowledge graph in Neo4j
  - Performs Root Cause Analysis (RCA)
  - Creates relationships between resources and incidents
- **Port:** 9090 (or 9091, 9092, 9093+ for multi-client)
- **Multi-tenant impact:** ✅ **THIS IS DUPLICATED PER CLIENT**
- **Current behavior:** One instance per client_id with separate consumer groups
- **Consumer groups:** Auto-created by Kafka (e.g., `kg-builder-prod-us-east-1`)

📖 **See [CONSUMER-GROUP-MANAGEMENT.md](./CONSUMER-GROUP-MANAGEMENT.md) for consumer group details**

## API & Visualization (Shared - Never Duplicated)

### 7. **KG API** (`kg-api`)
- **What it does:** REST API for querying the knowledge graph
- **Port:** 8080
- **Endpoints:** `/query`, `/rca`, `/incidents`, etc.
- **Multi-tenant impact:** ❌ No change - but queries should filter by `client_id`
- **Security:** Uses `KG_API_KEY` for authentication

### 8. **Prometheus** (`kg-prometheus`)
- **What it does:** Collects metrics from graph-builder instances
- **Port:** 9091 (external, not 9090 to avoid conflict)
- **Multi-tenant impact:** ⚠️ Config needs update to scrape all graph-builder instances
- **Scrapes:**
  - Single-tenant: `kg-graph-builder:9090`
  - Multi-tenant: `kg-graph-builder-client-a:9090`, `kg-graph-builder-client-b:9090`, etc.

### 9. **Grafana** (`kg-grafana`)
- **What it does:** Visualizes metrics and graph data
- **Port:** 3000
- **Dashboards:** Graph builder metrics, Neo4j stats, Kafka lag
- **Multi-tenant impact:** ❌ No change - shows all clients' metrics

## Optional Services

### 10. **Kafka Proxy** (`kg-kafka-proxy`)
- **What it does:** Nginx reverse proxy for SSL/TLS termination
- **Port:** 443
- **Multi-tenant impact:** ❌ No change

---

## Multi-Tenant Impact Summary

| Service | Instances | Multi-Tenant Changes |
|---------|-----------|---------------------|
| Zookeeper | 1 | None |
| Kafka | 1 | None - shared topics |
| Neo4j | 1 | None - shared DB with `client_id` |
| Kafka UI | 1 | None |
| **Alerts Enricher** | 1 | ⚠️ Could add CLIENT_ID filtering |
| **Graph Builder** | **N (1 per client)** | ✅ **Duplicated per client** |
| KG API | 1 | None - but queries filter by client_id |
| Prometheus | 1 | ⚠️ Needs config update for multi scrape |
| Grafana | 1 | None |
| Kafka Proxy | 1 | None |

---

## What Gets Duplicated in Multi-Tenant Setup?

### ✅ Only Graph Builder Gets Duplicated

When you run the multi-tenant setup, **only the graph-builder service gets duplicated**:

```
Single-Tenant:
└── kg-graph-builder (processes all clients)

Multi-Tenant:
├── kg-graph-builder-client-a (processes client-a only)
├── kg-graph-builder-client-b (processes client-b only)
└── kg-graph-builder-client-c (processes client-c only)
```

**Everything else stays the same!**

### Why Only Graph Builder?

The graph-builder is duplicated because:
1. **Performance isolation** - Each client's processing is independent
2. **Consumer groups** - Each needs its own Kafka consumer group
3. **Parallel processing** - Multiple instances process messages simultaneously
4. **Resource allocation** - Can allocate different resources per client

---

## Should Alerts Enricher Be Multi-Tenant?

Currently `alerts-enricher` processes all clients together in a single instance.

### Current Behavior
```
Client A events →                           → alerts.enriched (all clients mixed)
Client B events → → alerts-enricher (1) → →
Client C events →
```

### Options

**Option A: Keep Single Instance (Current)**
- ✅ Simpler
- ✅ Less resource usage
- ⚠️ No per-client isolation
- Works fine if enrichment is stateless

**Option B: Duplicate Per Client**
- ✅ Full isolation
- ✅ Independent failure domains
- ❌ More containers
- ❌ More complexity

**Recommendation:** Keep single instance unless you need per-client isolation or it becomes a bottleneck.

---

## Resource Usage Per Client

When adding a new client (one more graph-builder):

| Resource | Per Client |
|----------|------------|
| CPU | 0.5-1 core |
| Memory | 512MB-1GB |
| Network | Minimal (local) |
| Disk | None (data in Neo4j/Kafka) |

**Example:** 10 clients = ~10GB RAM for all graph-builders

---

## Service Dependencies

```
┌─────────────┐
│  Zookeeper  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Kafka    │◄─── All clients write here
└──┬───────┬──┘
   │       │
   │       └────────────────────┐
   │                            │
   ▼                            ▼
┌──────────────┐        ┌──────────────┐
│   Alerts     │        │    Graph     │ (x N clients)
│  Enricher    │        │   Builder    │
└──────┬───────┘        └──────┬───────┘
       │                       │
       └───────────┬───────────┘
                   ▼
            ┌─────────────┐
            │    Neo4j    │◄─── All data stored here
            └──────┬──────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
    ┌─────────┐         ┌─────────┐
    │ KG API  │         │ Grafana │
    └─────────┘         └─────────┘
```

---

## Monitoring Multi-Tenant Deployment

### Check All Graph Builders
```bash
docker compose -f compose/docker-compose.yml ps | grep graph-builder
```

### Check Consumer Groups
```bash
# List all consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list

# Expected output:
# kg-builder-client-a
# kg-builder-client-b
# kg-builder-client-c
# alerts-enricher
```

### Check Metrics Per Client
```bash
curl http://localhost:9091/metrics  # Client A
curl http://localhost:9092/metrics  # Client B
curl http://localhost:9093/metrics  # Client C
```

### Check Neo4j Data Distribution
```cypher
// Count resources per client
MATCH (r:Resource)
RETURN r.client_id, count(*) as count
ORDER BY count DESC
```

---

## Common Questions

### Q: Do I need multiple Kafka topics per client?
**A:** No! All clients share the same topics. Messages are distinguished by `client_id` field.

### Q: Do I need multiple Neo4j databases?
**A:** No! Single database with `client_id` property on all nodes.

### Q: Will adding clients slow down the system?
**A:** No - each graph-builder processes independently in parallel.

### Q: What happens if one graph-builder crashes?
**A:** Only that client is affected. Other clients continue processing normally.

### Q: Can I have different RCA settings per client?
**A:** Yes! Each graph-builder has its own environment variables for RCA_WINDOW_MIN, etc.

---

## Next Steps

1. ✅ Keep infrastructure as-is (Kafka, Neo4j, etc.)
2. ✅ Duplicate only graph-builders per client
3. ⚠️ Consider updating Prometheus config to scrape all graph-builders
4. ⚠️ Optionally add CLIENT_ID filtering to alerts-enricher if needed
5. ✅ Use dynamic discovery scripts to auto-generate configurations

For more details, see:
- [MULTI-TENANT-SETUP.md](./MULTI-TENANT-SETUP.md)
- [DYNAMIC-CLIENT-DISCOVERY.md](./DYNAMIC-CLIENT-DISCOVERY.md)
