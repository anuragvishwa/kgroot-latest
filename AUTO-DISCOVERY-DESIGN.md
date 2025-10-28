# Auto-Discovery Design - Zero-Touch Multi-Tenant

## Problem Statement

**Current System (Manual):**
- Install Helm chart: `client.id="af-10"`
- Start graph-builder: `CLIENT_ID=af-10`
- Manually ensure they match!
- Need 10 graph-builders for 10 clusters
- No automatic cleanup when cluster is deleted

**Desired System (Auto-Discovery):**
- Install Helm chart: `client.id="af-10"`
- **One graph-builder auto-discovers all clusters**
- Automatic tenant isolation
- Automatic cleanup of dead clusters

---

## Design Options

### Option 1: Kafka Message Key Prefix ⭐ **RECOMMENDED**

**How It Works:**
```
Event-Exporter sends:
  Key: "af-10::event-uid-123"
  Value: {"metadata": {...}, "reason": "Pulled"}

Graph-Builder receives:
  Extracts client_id from key: "af-10"
  Adds to event before storing
```

**Pros:**
- ✅ Simple - uses existing `splitTenantKey()` function
- ✅ No message body modification
- ✅ One graph-builder handles all clusters
- ✅ Clean separation (metadata in key, data in value)

**Cons:**
- ⚠️ Requires adding `key` field to event-exporter config
- ⚠️ May not work if event-exporter doesn't support key templates

**Implementation:**
```yaml
# event-exporter config
receivers:
  - name: "kafka"
    kafka:
      key: "{{ .Values.client.id }}::{{ .InvolvedObject.UID }}"
```

---

### Option 2: Kafka Message Headers

**How It Works:**
```
Event-Exporter sends:
  Headers: {"client_id": "af-10"}
  Value: {"metadata": {...}, "reason": "Pulled"}

Graph-Builder receives:
  Reads header: client_id = "af-10"
  Adds to event before storing
```

**Pros:**
- ✅ Clean metadata separation
- ✅ Kafka native feature
- ✅ One graph-builder handles all clusters

**Cons:**
- ❌ Event-exporter doesn't support custom headers
- ❌ Would require custom event-exporter build
- ❌ More complex implementation

---

### Option 3: Add client_id to Message Body

**How It Works:**
```
Event-Exporter sends:
  Value: {
    "client_id": "af-10",  ← Added by event-exporter
    "metadata": {...},
    "reason": "Pulled"
  }
```

**Pros:**
- ✅ Simple to implement
- ✅ One graph-builder handles all clusters
- ✅ client_id travels with data

**Cons:**
- ❌ Event-exporter layout templates have YAML issues (tried in v1.0.40-46)
- ❌ Modifies original Kubernetes events
- ❌ Double-encoding problems

**Status:** ❌ Already attempted and failed (v1.0.40-46)

---

### Option 4: Topic-Per-Cluster

**How It Works:**
```
Cluster af-10 → af-10.events.normalized
Cluster af-11 → af-11.events.normalized
Cluster af-12 → af-12.events.normalized

Graph-Builder:
  Subscribes to pattern: *.events.normalized
  Extracts client_id from topic name
```

**Pros:**
- ✅ Simple extraction from topic name
- ✅ One graph-builder handles all clusters
- ✅ Natural isolation

**Cons:**
- ❌ Topic sprawl (7 topics × 100 clusters = 700 topics!)
- ❌ Harder to manage permissions
- ❌ More Kafka overhead

---

### Option 5: Consumer Metadata Analysis

**How It Works:**
```
Graph-Builder analyzes Kafka metadata:
  - Producer client IDs: "event-exporter-af-10"
  - Consumer groups: Various

Extracts client_id patterns:
  - af-10 from "event-exporter-af-10"
  - af-11 from "state-watcher-af-11"
```

**Pros:**
- ✅ No client-side changes
- ✅ Automatic discovery from metadata

**Cons:**
- ❌ Complex heuristics
- ❌ Unreliable (producer IDs might not have client_id)
- ❌ Can't determine which message is from which cluster

---

### Option 6: Vector Aggregator Pattern

**How It Works:**
```
Kubernetes Cluster:
  Event-Exporter → Vector (local)
  State-Watcher → Vector (local)
  Logs → Vector (local)

Vector:
  Adds client_id to all messages
  Sends enriched data to Kafka

Graph-Builder:
  Reads client_id from message body
```

**Pros:**
- ✅ Centralized enrichment point
- ✅ Vector already deployed
- ✅ One graph-builder handles all clusters

**Cons:**
- ⚠️ Requires rewriting all data flows through Vector
- ⚠️ Vector becomes single point of failure
- ⚠️ More complex architecture

---

## Recommended Solution: **Option 1 (Kafka Message Key)**

### Implementation Steps

#### 1. Update Event-Exporter (Client-Side)

```yaml
# client-light/helm-chart/templates/event-exporter-deployment.yaml
receivers:
  - name: "kafka"
    kafka:
      brokers:
        - {{ .Values.client.kafka.brokers }}
      topic: events.normalized
      key: "{{ .Values.client.id }}::{{ "{{" }} .InvolvedObject.UID {{ "}}" }}"
      compression: gzip
```

**Result:** Kafka messages have key like `"af-10::event-uid-123"`

#### 2. Update State-Watcher (Already Has Key Support)

State-watcher already sends Kafka keys, just need to ensure client_id prefix:

```go
// kg-state-watcher already does:
key := fmt.Sprintf("%s::%s", clientID, resourceUID)
```

✅ No changes needed!

#### 3. Update Vector (Logs)

```toml
# Vector config
[sinks.kafka_logs]
type = "kafka"
topic = "logs.normalized"
encoding.codec = "json"
key_field = "message_key"  # Use computed field as key

[sinks.kafka_logs.transforms]
add_message_key = '''
  .message_key = "{{ .Values.client.id }}::" + .pod_uid
'''
```

#### 4. Update Graph-Builder (Server-Side)

Make CLIENT_ID optional and extract from key:

```go
// kg/graph-builder.go

// Current code already has splitTenantKey()!
tenantFromKey, rawKey := splitTenantKey(string(msg.Key))

// Just use it as primary source:
if ev.ClientID == "" && tenantFromKey != "" {
    ev.ClientID = tenantFromKey  // ← Already exists!
}
// Fallback to env var only if key has no client_id
if ev.ClientID == "" && h.clientID != "" {
    ev.ClientID = h.clientID
}
```

**Changes Needed:** Just reorder the fallback logic! (Already exists)

#### 5. Deploy Single Graph-Builder

```yaml
# docker-compose.yml on mini-server
kg-graph-builder:
  image: anuragvishwa/kg-graph-builder:1.0.21
  environment:
    # NO CLIENT_ID env var - auto-discovery mode!
    KAFKA_BROKERS: "kafka:9092"
    KAFKA_GROUP: "kg-builder-multi-tenant"
    NEO4J_URI: "neo4j://neo4j:7687"
```

**Result:** One graph-builder handles af-10, af-11, af-12, etc. automatically!

---

## Benefits of Auto-Discovery

### Before (Manual - v1.0.47)

```
10 Kubernetes Clusters
  ↓
10 Manual Configurations
  ↓
10 Graph-Builders (CLIENT_ID=af-10, af-11, ...)
  ↓
10 Consumer Groups
  ↓
Manual Cleanup Required
```

**Cost:** 10 × (1.7% CPU + 10 MB memory) = 17% CPU, 100 MB

### After (Auto-Discovery - v1.1.0)

```
10 Kubernetes Clusters
  ↓
Automatic Discovery from Kafka Keys
  ↓
1 Graph-Builder (auto-discovery mode)
  ↓
1 Consumer Group
  ↓
Automatic Cleanup (no unused consumers!)
```

**Cost:** 1 × (10% CPU + 50 MB memory) = 10% CPU, 50 MB

### Comparison

| Metric | Manual (v1.0.47) | Auto-Discovery (v1.1.0) |
|--------|------------------|-------------------------|
| Graph-Builders | 10 instances | 1 instance |
| Configuration | Manual per cluster | Zero-touch |
| CPU Usage | 17% | ~10% |
| Memory | 100 MB | ~50 MB |
| Consumer Groups | 10 | 1 |
| Cleanup | Manual | Automatic |
| Cluster Addition | Deploy new graph-builder | Just install Helm chart! |
| Cluster Removal | Manual cleanup | Automatic (no more messages) |

---

## Migration Path

### Phase 1: Add Key Support (Non-Breaking)

1. Update Helm chart to add key field
2. Messages have BOTH:
   - Key: `af-10::uid` (new)
   - Body: Clean event (existing)
3. Old graph-builders still work (use CLIENT_ID env var)
4. New graph-builder can use key

**Status:** Non-breaking change ✅

### Phase 2: Deploy Multi-Tenant Graph-Builder

1. Deploy new graph-builder without CLIENT_ID
2. Run in parallel with old graph-builders
3. Verify it extracts client_id from keys
4. Monitor for 24 hours

### Phase 3: Cutover

1. Stop old graph-builders
2. Delete old consumer groups
3. Single graph-builder handles all clusters
4. Profit! 🎉

---

## Fallback Strategy

If auto-discovery fails or has issues:

```yaml
# Can always add CLIENT_ID back
kg-graph-builder:
  environment:
    CLIENT_ID: "af-10"  # Override auto-discovery
```

**Result:** Falls back to single-tenant mode (current behavior)

---

## Alternative: Keep Current System

If you prefer NOT to change anything:

**Pros of Current System:**
- ✅ Simple and working
- ✅ Explicit configuration (clear what handles what)
- ✅ Isolated failures (one graph-builder crash doesn't affect others)

**Cons of Current System:**
- ❌ Manual coordination required
- ❌ More resource usage (10× instances)
- ❌ Manual cleanup when clusters are removed
- ❌ Operational overhead

**Verdict:** Current system is fine for < 10 clusters. Auto-discovery becomes valuable at 20+ clusters.

---

## Recommendation

### For Your Current Setup (1 cluster: af-10)
**Keep v1.0.47** - It works perfectly and is simple

### For Future Growth (10+ clusters)
**Implement Option 1 (Kafka Key)** - Best balance of simplicity and automation

### For Massive Scale (100+ clusters)
**Implement Option 4 (Topic-Per-Cluster)** - Better isolation despite topic sprawl

---

## Next Steps

**If proceeding with auto-discovery:**

1. ✅ Update event-exporter template (add key field)
2. ✅ Update graph-builder (reorder client_id extraction)
3. ✅ Test with 2 clusters (af-10, af-11)
4. ✅ Document migration procedure
5. ✅ Publish v1.1.0

**If keeping current system:**

1. ✅ Document current manual coordination process
2. ✅ Create cluster lifecycle management guide
3. ✅ Automate consumer cleanup scripts
4. ✅ Done! System is production-ready as-is

---

## Decision?

What's your preference?

**A)** Implement auto-discovery (Option 1 - Kafka Key)
**B)** Keep current manual system (works great for few clusters)
**C)** Different approach (which option?)

Let me know and I'll proceed accordingly!
