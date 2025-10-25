# Control Plane Architecture (Pure Model)

## 🎯 Overview

This document describes the **pure control plane model** for multi-client RCA management, where client isolation is achieved through:

✅ **Consumer groups** (not message filtering)
✅ **Kafka key partitioning** (not embedded client_id in payloads)
✅ **Dynamic container spawning** (per-client normalizers and graph builders)
✅ **Heartbeat monitoring** (automatic cleanup of stale clients)

**Key Principle**: Client ID exists ONLY in Kafka keys, NOT in message payloads.

---

## 🏗️ Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CLIENT K8S CLUSTER (af-9)                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  1. Client Registers (ONE TIME)                                      │
│     ↓                                                                 │
│  Kafka Topic: cluster.registry                                       │
│    Key: "af-9"                                                        │
│    Value: {                                                           │
│      "client_id": "af-9",  ← Only here for registration              │
│      "cluster_name": "production-us-east",                            │
│      "k8s_version": "1.28"                                            │
│    }                                                                  │
│                                                                       │
│  2. Client Sends Heartbeats (Every 30s)                              │
│     ↓                                                                 │
│  Kafka Topic: cluster.heartbeat                                      │
│    Key: "af-9"                                                        │
│    Value: {                                                           │
│      "client_id": "af-9",                                             │
│      "timestamp": "2025-01-20T10:30:00Z"                              │
│    }                                                                  │
│                                                                       │
│  3. Client Publishes Events (NO client_id in payload!)               │
│     ↓                                                                 │
│  Kafka Topic: raw.k8s.events (SHARED with all clients)               │
│    Key: "af-9::k8s-event::abc123"  ← Client ID ONLY in key           │
│    Value: {                                                           │
│      "event_id": "evt-abc123",     ← NO client_id field!             │
│      "reason": "OOMKilled",                                           │
│      "message": "Container memory limit exceeded",                    │
│      ...                                                              │
│    }                                                                  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  │  Kafka shared topics
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    SERVER (Docker Compose)                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              CONTROL PLANE MANAGER (Single Container)           │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │                                                                  │  │
│  │  Monitors:                                                       │  │
│  │    - cluster.registry  (detects new clients)                    │  │
│  │    - cluster.heartbeat (monitors client health)                 │  │
│  │                                                                  │  │
│  │  Actions:                                                        │  │
│  │    1. Client "af-9" registers                                   │  │
│  │       → Spawns: kg-event-normalizer-af-9                        │  │
│  │       → Spawns: kg-log-normalizer-af-9                          │  │
│  │       → Spawns: kg-graph-builder-af-9                           │  │
│  │                                                                  │  │
│  │    2. No heartbeat for 2 minutes                                │  │
│  │       → Stops and removes all af-9 containers                   │  │
│  │                                                                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                  │                                   │
│                                  │ Spawns per-client containers      │
│                                  ▼                                   │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │         PER-CLIENT CONTAINERS (Spawned Dynamically)             │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │                                                                  │  │
│  │  kg-event-normalizer-af-9                                       │  │
│  │    ├─ Env: CLIENT_ID=af-9                                       │  │
│  │    ├─ Consumer Group: "event-normalizer-af-9" ← Unique!        │  │
│  │    ├─ Reads: raw.k8s.events (shared topic)                      │  │
│  │    │   - Kafka auto-assigns partitions based on key hash        │  │
│  │    │   - Only gets messages with key prefix "af-9::"            │  │
│  │    └─ Writes: events.normalized (shared topic)                  │  │
│  │        Key: "af-9::evt-abc123"                                   │  │
│  │        Value: {NO client_id field!}                              │  │
│  │                                                                  │  │
│  │  kg-log-normalizer-af-9                                         │  │
│  │    ├─ Env: CLIENT_ID=af-9                                       │  │
│  │    ├─ Consumer Group: "log-normalizer-af-9"                     │  │
│  │    ├─ Reads: raw.k8s.logs (shared topic)                        │  │
│  │    └─ Writes: logs.normalized (shared topic)                    │  │
│  │                                                                  │  │
│  │  kg-graph-builder-af-9                                          │  │
│  │    ├─ Env: CLIENT_ID=af-9, NEO4J_DATABASE=af-9                 │  │
│  │    ├─ Consumer Group: "graph-builder-af-9"                      │  │
│  │    ├─ Reads: events.normalized, logs.normalized                 │  │
│  │    └─ Writes: Neo4j database "af-9" (isolated!)                │  │
│  │                                                                  │  │
│  │  ─────────────────────────────────────────────────────────      │  │
│  │                                                                  │  │
│  │  kg-event-normalizer-af-10  (for client af-10)                 │  │
│  │  kg-log-normalizer-af-10                                        │  │
│  │  kg-graph-builder-af-10                                         │  │
│  │    ...                                                           │  │
│  │                                                                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Concepts

### 1. Client ID Location

| Component | Where client_id Exists | Example |
|-----------|------------------------|---------|
| **Kafka Key** | ✅ YES | `"af-9::evt-abc123"` |
| **Message Payload** | ❌ NO | `{"event_id": "evt-abc123", ...}` |
| **Consumer Group** | ✅ YES | `"event-normalizer-af-9"` |
| **Container Name** | ✅ YES | `kg-event-normalizer-af-9` |
| **Neo4j Database** | ✅ YES | Database name: `af-9` |

### 2. Consumer Group Isolation

Each client gets **dedicated consumer groups**:

```python
# Client af-9
Consumer(
    topic='raw.k8s.events',
    group_id='event-normalizer-af-9'  # ← Unique per client
)

# Client af-10
Consumer(
    topic='raw.k8s.events',
    group_id='event-normalizer-af-10'  # ← Different group
)
```

**Kafka automatically partitions by key hash:**
- Messages with key `"af-9::*"` → Partition X → Consumer group `af-9`
- Messages with key `"af-10::*"` → Partition Y → Consumer group `af-10`

### 3. Message Flow Example

**Client af-9 publishes event:**
```json
Topic: raw.k8s.events
Key: "af-9::k8s-event::abc123"
Value: {
  "event_id": "evt-abc123",
  "reason": "OOMKilled",
  "message": "...",
  // NO client_id field!
}
```

**Event normalizer af-9 consumes:**
```python
# Container: kg-event-normalizer-af-9
# Env: CLIENT_ID=af-9
# Consumer group: event-normalizer-af-9

for message in consumer:
    kafka_key = message.key  # "af-9::k8s-event::abc123"
    client_from_key = kafka_key.split("::")[0]  # "af-9"

    # Verify (safety check, should always match)
    assert client_from_key == os.getenv("CLIENT_ID")

    # Process event...
    normalized = normalize(message.value)

    # Publish with same key structure
    producer.send(
        'events.normalized',
        key=f"af-9::{normalized.event_id}",
        value=normalized.to_dict()  # Still NO client_id in payload!
    )
```

---

## 📊 Kafka Topics (Shared Across All Clients)

| Topic | Purpose | Key Format | Payload Contains client_id? |
|-------|---------|------------|-----------------------------|
| **cluster.registry** | Client registration | `{client-id}` | ✅ YES (registration only) |
| **cluster.heartbeat** | Health monitoring | `{client-id}` | ✅ YES (heartbeat only) |
| **raw.k8s.events** | Raw events | `{client-id}::event::{uid}` | ❌ NO |
| **raw.k8s.logs** | Raw logs | `{client-id}::log::{uid}` | ❌ NO |
| **events.normalized** | Structured events | `{client-id}::evt-{id}` | ❌ NO |
| **logs.normalized** | Structured logs | `{client-id}::log-{id}` | ❌ NO |
| **state.k8s.topology** | Dependency graph | `{client-id}::topology` | ❌ NO |
| **alerts.raw** | Prometheus alerts | `{client-id}::alert::{uid}` | ❌ NO |

**Result**: Clean messages, no payload pollution!

---

## 🚀 Control Plane Lifecycle

### Phase 1: Client Registration

```
1. Client af-9 sends registration message
   ↓
   Kafka: cluster.registry
   Key: "af-9"
   Value: {"client_id": "af-9", "cluster_name": "production", ...}

2. Control Plane detects new registration
   ↓
   Spawns containers:
     - kg-event-normalizer-af-9 (env: CLIENT_ID=af-9)
     - kg-log-normalizer-af-9 (env: CLIENT_ID=af-9)
     - kg-graph-builder-af-9 (env: CLIENT_ID=af-9, NEO4J_DATABASE=af-9)

3. Each container starts consuming with unique consumer group
   ↓
   Kafka automatically routes messages by key hash
```

### Phase 2: Normal Operation

```
Client af-9:
  - Publishes events every few seconds → raw.k8s.events (key: "af-9::*")
  - Publishes heartbeat every 30s → cluster.heartbeat (key: "af-9")

kg-event-normalizer-af-9:
  - Consumes from raw.k8s.events (consumer group: "event-normalizer-af-9")
  - Only receives messages with key prefix "af-9::" (Kafka partitioning)
  - Normalizes and publishes to events.normalized (key: "af-9::evt-*")

kg-graph-builder-af-9:
  - Consumes from events.normalized (consumer group: "graph-builder-af-9")
  - Builds FPG/FEKG for client af-9
  - Writes to Neo4j database "af-9"
```

### Phase 3: Client Goes Offline

```
1. Client af-9 stops sending heartbeats
   ↓
   Last heartbeat: 2025-01-20T10:30:00Z

2. Control Plane checks every 30 seconds
   ↓
   After 2 minutes (10:32:00Z), detects stale client

3. Control Plane cleans up:
   ↓
   docker stop kg-event-normalizer-af-9
   docker stop kg-log-normalizer-af-9
   docker stop kg-graph-builder-af-9
   docker rm kg-event-normalizer-af-9
   docker rm kg-log-normalizer-af-9
   docker rm kg-graph-builder-af-9

4. Consumer groups automatically removed by Kafka
   ↓
   Kafka garbage collects inactive groups after 24 hours
```

### Phase 4: Client Reconnects

```
1. Client af-9 registers again
   ↓
   Sends registration to cluster.registry (same client_id)

2. Control Plane detects registration
   ↓
   Spawns containers again (fresh start)

3. Containers resume from last committed offset
   ↓
   Consumer groups pick up where they left off (if within retention)
   OR start from latest (if retention expired)
```

---

## 🎯 Benefits vs Embedded client_id

| Feature | Embedded client_id | Control Plane Model |
|---------|-------------------|---------------------|
| **Message Size** | Larger (+10-50 bytes per message) | Smaller (no client_id in payload) |
| **Bandwidth** | Higher | Lower (10-20% savings) |
| **Consumer Complexity** | Simple (one consumer, filter in code) | Moderate (control plane needed) |
| **Isolation** | Logical (filter-based) | Physical (separate consumer groups) |
| **Neo4j Isolation** | Manual (WHERE client_id='af-9') | Automatic (separate databases) |
| **Scalability** | Limited (single consumer bottleneck) | Excellent (parallel consumers) |
| **Dynamic Scaling** | Manual | Automatic (control plane spawns/kills) |
| **Cleanup** | Manual | Automatic (heartbeat-based) |

---

## 🔧 Configuration

### Control Plane Settings

```yaml
# docker-compose-control-plane.yml
kg-control-plane:
  image: anuragvishwa/kg-control-plane:2.0.0
  environment:
    KAFKA_BROKERS: "kg-kafka:29092"
    DOCKER_NETWORK: "mini-server-prod_kg-network"
    STALE_CLIENT_THRESHOLD_MINUTES: "2"  # Cleanup after 2 min no heartbeat
    HEARTBEAT_CHECK_INTERVAL_SECONDS: "30"  # Check every 30s
```

### Client Settings

```yaml
# Client Helm values
client:
  id: "af-9"  # Must be unique per cluster

clusterRegistry:
  enabled: true
  registryTopic: "cluster.registry"
  heartbeatTopic: "cluster.heartbeat"
  heartbeatInterval: "30s"

# All publishers use Kafka key format:
# "{client.id}::{entity-type}::{entity-id}"
```

---

## 📊 Monitoring

### Check Active Clients

```bash
# View registered clients
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.registry \
  --from-beginning

# Check recent heartbeats
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.heartbeat \
  --max-messages 10
```

### Check Spawned Containers

```bash
# List all client containers
docker ps | grep "kg-event-normalizer\|kg-log-normalizer\|kg-graph-builder"

# Expected output:
# kg-event-normalizer-af-9
# kg-log-normalizer-af-9
# kg-graph-builder-af-9
# kg-event-normalizer-af-10
# kg-log-normalizer-af-10
# kg-graph-builder-af-10
```

### Check Consumer Groups

```bash
# List all consumer groups (should see one per client per service)
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:29092 \
  --list | grep "af-9"

# Expected output:
# event-normalizer-af-9
# log-normalizer-af-9
# graph-builder-af-9

# Check lag for specific group
docker exec kg-kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:29092 \
  --describe --group event-normalizer-af-9
```

### Control Plane Logs

```bash
# Monitor control plane activity
docker logs kg-control-plane -f

# Expected output:
# 📋 New client registered: af-9
# 🚀 Spawning containers for client: af-9
#    ✅ Spawned event normalizer: kg-event-normalizer-af-9
#    ✅ Spawned log normalizer: kg-log-normalizer-af-9
#    ✅ Spawned graph builder: kg-graph-builder-af-9
# 💓 Heartbeat received from: af-9
# ⚠️  Client af-10 is stale (no heartbeat for 2+ min)
# 🧹 Cleaning up stale client: af-10
```

---

## 🧪 Testing

### Test 1: Register New Client

```bash
# Simulate client registration
docker exec kg-kafka kafka-console-producer.sh \
  --bootstrap-server localhost:29092 \
  --topic cluster.registry \
  --property "parse.key=true" \
  --property "key.separator=:"

# Input:
test-client-001:{"client_id":"test-client-001","cluster_name":"test","k8s_version":"1.28"}

# Check if containers spawned:
docker ps | grep test-client-001

# Expected:
# kg-event-normalizer-test-client-001
# kg-log-normalizer-test-client-001
# kg-graph-builder-test-client-001
```

### Test 2: Send Event for Client

```bash
# Publish event with client key
docker exec kg-kafka kafka-console-producer.sh \
  --bootstrap-server localhost:29092 \
  --topic raw.k8s.events \
  --property "parse.key=true" \
  --property "key.separator=|"

# Input:
test-client-001::event::abc|{"event_id":"evt-123","reason":"OOMKilled","message":"Test event"}

# Check if normalizer processed it:
docker logs kg-event-normalizer-test-client-001 --tail 20

# Check normalized output:
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:29092 \
  --topic events.normalized \
  --from-beginning \
  --property print.key=true \
  --max-messages 1
```

### Test 3: Simulate Client Going Offline

```bash
# Stop sending heartbeats (wait 2+ minutes)
# Control plane should auto-cleanup

# After 2 minutes, check:
docker ps | grep test-client-001
# Should return nothing (containers removed)

docker logs kg-control-plane --tail 20
# Should show:
# ⚠️  Client test-client-001 is stale
# 🧹 Cleaning up stale client: test-client-001
```

---

## 🚀 Advantages of This Model

1. **Clean Messages**: No client_id pollution in payloads (10-20% bandwidth savings)
2. **Automatic Isolation**: Kafka partitioning + consumer groups handle routing
3. **Dynamic Scaling**: Control plane spawns/kills containers automatically
4. **Neo4j Isolation**: Separate database per client (no cross-client queries)
5. **Fault Tolerance**: If normalizer crashes, only one client affected
6. **Resource Efficiency**: Idle clients cleaned up automatically
7. **Operational Simplicity**: No manual container management

---

## 📚 Next Steps

1. **Deploy Control Plane V2**: Update docker-compose to use control_plane_manager_v2.py
2. **Update Normalizers**: Use event_normalizer_v2.py (client_id from env, not payload)
3. **Update Client Helm**: Ensure Kafka keys include client_id prefix
4. **Test End-to-End**: Register client → Send events → Verify containers spawned
5. **Monitor**: Watch control plane logs for automatic lifecycle management

---

**🎉 With pure control plane model, you get clean architecture, automatic scaling, and perfect multi-client isolation!**
