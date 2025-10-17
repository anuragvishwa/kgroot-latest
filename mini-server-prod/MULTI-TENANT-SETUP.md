# Multi-Tenant Knowledge Graph Setup

## Overview

The knowledge graph system now supports **multi-tenant deployments** where multiple clients can send data to the same Kafka topics, and separate graph-builder instances process messages for each client independently.

## Architecture

### Key Components

1. **Client-Side (Data Producers)**
   - Each client deployment includes a `client_id` in all messages
   - All clients write to the same Kafka topics
   - Messages are distinguished by the `client_id` field

2. **Server-Side (Graph Builders)**
   - Run one graph-builder instance per client
   - Each instance filters messages by `CLIENT_ID` environment variable
   - Uses client-specific Kafka consumer groups
   - Writes to shared Neo4j with `client_id` namespace

3. **Storage (Neo4j)**
   - Single shared Neo4j instance
   - All nodes include `client_id` property
   - Indexed for efficient filtering

## Deployment Options

### Option 1: Single Graph Builder (All Clients)

Process messages from all clients in one graph-builder instance:

```yaml
# In docker-compose.yml or .env
CLIENT_ID=  # Empty = process all clients
```

**Use case:** Single-tenant deployment or when all clients share the same knowledge graph.

### Option 2: Multiple Graph Builders (Per-Client)

Run separate graph-builder instances for each client. There are two approaches:

#### Option 2a: Static Configuration

Use predefined client IDs in `docker-compose.multi-client.yml`:

```bash
docker compose -f docker-compose.yml -f docker-compose.multi-client.yml up -d
```

**Pros:** Pre-provision clients before they send data
**Cons:** Must manually update when clients change

#### Option 2b: Dynamic Discovery (Recommended)

Automatically discover client IDs from Kafka and generate configuration:

```bash
# Discover and generate config based on actual client_ids in Kafka
./generate-multi-client-compose.sh

# Deploy with auto-generated config
docker compose -f docker-compose.yml -f docker-compose.multi-client.generated.yml up -d
```

**Pros:** Auto-adapts to real clients, no hardcoding
**Cons:** Requires clients to be sending data first

📖 **See [DYNAMIC-CLIENT-DISCOVERY.md](./DYNAMIC-CLIENT-DISCOVERY.md) for detailed instructions**

**Use case:** Multi-tenant SaaS deployment with isolated knowledge graphs per client.

## Configuration

### Client-Side Setup

Update your Vector daemonset to include `client_id` in all messages:

**File:** `client-light/helm-chart/values.yaml`

```yaml
client:
  id: "client-a"  # Unique identifier for this client
  kafka:
    brokers: "your-kafka-server:9092"
```

The Vector configuration automatically adds `client_id` to all messages:

```toml
.client_id = "{{ .Values.client.id }}"
```

### Server-Side Setup

#### Single Client Deployment

**File:** `mini-server-prod/.env`

```bash
# Process only messages from client-a
CLIENT_ID=client-a
```

#### Multi-Client Deployment

Create a custom docker-compose override:

```yaml
# docker-compose.multi-client.yml
services:
  graph-builder-client-a:
    environment:
      CLIENT_ID: client-a
    ports:
      - "9091:9090"

  graph-builder-client-b:
    environment:
      CLIENT_ID: client-b
    ports:
      - "9092:9090"
```

Start all services:

```bash
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.multi-client.yml \
  up -d
```

## How It Works

### Message Flow

```
┌─────────────────────────────────────────────────────────────┐
│                         Client A                            │
│  (Kubernetes Cluster + Vector Agent)                        │
│  client_id: "client-a"                                      │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌─────────────────┴────────────────────────────────────────────┐
│                         Client B                             │
│  (Kubernetes Cluster + Vector Agent)                         │
│  client_id: "client-b"                                       │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  Kafka Topics   │
         │  - logs.normalized
         │  - events.normalized
         │  - state.k8s.resource
         │  - state.k8s.topology
         └────┬────────┬───┘
              │        │
      ┌───────┘        └──────┐
      ▼                       ▼
┌──────────────┐      ┌──────────────┐
│ Graph Builder│      │ Graph Builder│
│  CLIENT_ID:  │      │  CLIENT_ID:  │
│  "client-a"  │      │  "client-b"  │
│              │      │              │
│ Consumer Grp:│      │ Consumer Grp:│
│ kg-builder-  │      │ kg-builder-  │
│ client-a     │      │ client-b     │
└──────┬───────┘      └──────┬───────┘
       │                     │
       └──────────┬──────────┘
                  ▼
         ┌─────────────────┐
         │     Neo4j       │
         │                 │
         │ Nodes have      │
         │ client_id field │
         └─────────────────┘
```

### Consumer Group Naming

Each graph-builder automatically creates a client-specific consumer group:

- Base group: `kg-builder`
- With CLIENT_ID: `kg-builder-{client_id}`

Examples:
- `CLIENT_ID=client-a` → Consumer group: `kg-builder-client-a`
- `CLIENT_ID=client-b` → Consumer group: `kg-builder-client-b`

This ensures:
1. Each client's messages are processed independently
2. No message duplication between clients
3. Parallel processing for better performance

### Neo4j Data Model

All Resource nodes include `client_id`:

```cypher
// Example Resource node for client-a
(r:Resource:Pod {
  rid: "pod:default:nginx-abc",
  client_id: "client-a",
  ns: "default",
  name: "nginx-abc",
  ...
})

// Example Resource node for client-b
(r:Resource:Pod {
  rid: "pod:default:nginx-xyz",
  client_id: "client-b",
  ns: "default",
  name: "nginx-xyz",
  ...
})
```

### Querying by Client

Use indexed `client_id` field for efficient queries:

```cypher
// Get all resources for client-a
MATCH (r:Resource {client_id: "client-a"})
RETURN r

// Get client-a incidents
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.client_id = "client-a"
  AND e.severity IN ['ERROR', 'FATAL']
RETURN e, r

// RCA for client-b only
MATCH (e:Episodic {eid: $event_id})-[:ABOUT]->(r:Resource {client_id: "client-b"})
MATCH (e)<-[:POTENTIAL_CAUSE]-(cause:Episodic)-[:ABOUT]->(cr:Resource {client_id: "client-b"})
RETURN cause, cr
ORDER BY cause.event_time DESC
```

## Monitoring

### Prometheus Metrics

Each graph-builder exposes metrics on different ports:

| Client | Metrics Port | Consumer Group |
|--------|--------------|----------------|
| All    | 9090         | kg-builder     |
| client-a | 9091       | kg-builder-client-a |
| client-b | 9092       | kg-builder-client-b |
| client-c | 9093       | kg-builder-client-c |

Access metrics:
```bash
# Client A metrics
curl http://localhost:9091/metrics

# Client B metrics
curl http://localhost:9092/metrics
```

### Kafka Consumer Lag

Monitor consumer lag for each client:

```bash
# Check all consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list

# Check client-a lag
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-client-a \
  --describe
```

### Neo4j Queries

Check data distribution:

```cypher
// Count resources per client
MATCH (r:Resource)
RETURN r.client_id, count(*) as resource_count
ORDER BY resource_count DESC

// Count events per client
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
RETURN r.client_id, count(DISTINCT e) as event_count
ORDER BY event_count DESC
```

## Performance Considerations

### Resource Allocation

Each graph-builder instance requires:
- **CPU:** 0.5-1 core
- **Memory:** 512MB-1GB
- **Network:** Minimal (local to Kafka)

Example resource limits:

```yaml
graph-builder-client-a:
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 1G
      reservations:
        cpus: '0.5'
        memory: 512M
```

### Kafka Partitioning

For optimal performance:
1. Use at least 3 partitions per topic
2. Partition by `client_id` for even distribution
3. Scale consumers per partition

Current partition strategy:
```toml
# In Vector config
key_field = "pod_uid"  # Can change to "client_id" for client-based partitioning
```

### Neo4j Optimization

With multiple clients:
1. **Indexes are critical** - Already created for `client_id`
2. **Connection pooling** - Each graph-builder maintains its own pool
3. **Query optimization** - Always filter by `client_id` in WHERE clauses

## Troubleshooting

### Messages Not Being Processed

**Check consumer group status:**
```bash
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group kg-builder-client-a \
  --describe
```

**Verify CLIENT_ID in logs:**
```bash
docker logs kg-graph-builder-client-a | grep "multi-tenant"
```

Expected output:
```
multi-tenant mode enabled: client_id=client-a, consumer_group=kg-builder-client-a
```

### Wrong Client Data in Graph

**Check message client_id:**
```bash
# Sample messages from Kafka
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic logs.normalized \
  --max-messages 5 \
  | jq '.client_id'
```

**Verify Neo4j data:**
```cypher
// Check for mixed client data
MATCH (r:Resource)
WHERE r.client_id <> "expected-client-id"
RETURN r.client_id, count(*) as unexpected_count
```

### Consumer Lag Increasing

**Possible causes:**
1. Too many messages for single consumer
2. Neo4j write bottleneck
3. RCA queries taking too long

**Solutions:**
```bash
# Scale by adding more partitions
docker exec kg-kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --topic logs.normalized \
  --alter --partitions 6

# Reduce RCA window for faster processing
CLIENT_ID=client-a RCA_WINDOW_MIN=5 docker-compose up -d
```

## Migration Guide

### From Single-Tenant to Multi-Tenant

**Step 1:** Add client_id to all client deployments

```yaml
# client-light/helm-chart/values.yaml
client:
  id: "production-cluster-1"
```

**Step 2:** Deploy with CLIENT_ID empty first (process all)

```bash
CLIENT_ID= docker-compose up -d graph-builder
```

**Step 3:** Verify messages have client_id

```bash
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic logs.normalized \
  --max-messages 10 \
  | jq '.client_id'
```

**Step 4:** Deploy client-specific graph-builders

```bash
docker-compose -f docker-compose.yml -f docker-compose.multi-client.yml up -d
```

**Step 5:** Remove original graph-builder

```bash
docker-compose stop graph-builder
docker-compose rm graph-builder
```

## API Integration

When querying the kg-api, filter by client_id:

```bash
# Get incidents for client-a
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (e:Episodic)-[:ABOUT]->(r:Resource {client_id: $client_id}) WHERE e.severity IN [\"ERROR\", \"FATAL\"] RETURN e, r LIMIT 10",
    "params": {
      "client_id": "client-a"
    }
  }'
```

## Best Practices

1. **Always set client_id** - Even in single-tenant deployments for future flexibility
2. **Use meaningful IDs** - Format: `{environment}-{cluster}-{region}` (e.g., `prod-us-east-1-cluster-a`)
3. **Monitor consumer lag** - Set alerts for lag > 1000 messages
4. **Index optimization** - Always include `client_id` in Neo4j query filters
5. **Resource planning** - Allocate 1GB RAM per 10k resources per client
6. **Backup strategy** - Consider per-client backup policies for large deployments

## Example Deployment

Complete example for 3 clients:

```bash
# Set environment
export KAFKA_ADVERTISED_HOST=your-server-ip
export NEO4J_PASSWORD=secure-password

# Deploy infrastructure
docker-compose up -d zookeeper kafka neo4j

# Deploy multi-client graph builders
docker-compose -f docker-compose.yml -f docker-compose.multi-client.yml up -d

# Verify all consumers are running
docker-compose ps | grep graph-builder

# Expected output:
# kg-graph-builder-client-a   Up   9091->9090/tcp
# kg-graph-builder-client-b   Up   9092->9090/tcp
# kg-graph-builder-client-c   Up   9093->9090/tcp

# Check consumer groups
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list | grep kg-builder

# Expected output:
# kg-builder-client-a
# kg-builder-client-b
# kg-builder-client-c
```

## Additional Resources

- [Main README](./README.md) - General setup instructions
- [Architecture Docs](./docs/ARCHITECTURE.md) - System architecture
- [Monitoring Guide](./docs/MONITORING.md) - Metrics and alerts
- [API Documentation](../kg-api/README.md) - Query API reference
