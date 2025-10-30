# Causality & Topology: How Relationships Are Created

## 🎯 TL;DR

**Causal Links (POTENTIAL_CAUSE)**: ✅ Created **on-demand** via API
**Topology Links (SELECTS, RUNS_ON, CONTROLS)**: ✅ Created **during event ingestion**

---

## 📊 The Two Types of Relationships

### 1. **Causal Relationships** (`POTENTIAL_CAUSE`)
**Purpose**: Link events by causality (Event A caused Event B)
**Created**: **On-demand** via API endpoint
**Confidence**: 0.0-1.0 based on multi-dimensional scoring

### 2. **Topology Relationships** (`SELECTS`, `RUNS_ON`, `CONTROLS`)
**Purpose**: Represent Kubernetes resource relationships
**Created**: **During event ingestion** (from K8s metadata)
**Examples**:
- `Service -[SELECTS]-> Pod`
- `Pod -[RUNS_ON]-> Node`
- `Deployment -[CONTROLS]-> ReplicaSet`

---

## 🔧 How POTENTIAL_CAUSE Relationships Are Created

### Current System: On-Demand API

Your **existing RCA API (port 8082/8083)** has an endpoint to build causality:

```bash
# Build causality relationships on-demand
POST http://localhost:8082/api/v1/rca/build-causality/{client_id}

Parameters:
- time_range_hours: 24 (default)
- min_confidence: 0.3 (default)
- build_relationships: true (default)
```

**Example:**
```bash
# Build causality for loc-01 client
curl -X POST "http://localhost:8082/api/v1/rca/build-causality/loc-01?time_range_hours=24&min_confidence=0.3&build_relationships=true"
```

**Response:**
```json
{
  "client_id": "loc-01",
  "status": "success",
  "events_analyzed": 1529,
  "relationships_before": 0,
  "relationships_after": 847,
  "relationships_created_or_updated": 847,
  "statistics": {
    "total_relationships": 847,
    "avg_confidence": 0.652,
    "max_confidence": 0.95,
    "min_confidence": 0.301
  },
  "processing_time_ms": 3420,
  "message": "Successfully built 847 POTENTIAL_CAUSE relationships with enhanced KGroot algorithm"
}
```

---

## 🧠 Enhanced Causality Algorithm (KGroot Paper)

The causality builder uses the **KGroot enhanced algorithm** with:

### 1. **Adaptive Time Windows**
```
Event Type          | Time Window
--------------------|-------------
OOMKilled, Error    | 2 minutes
ImagePull issues    | 5 minutes
FailedScheduling    | 15 minutes
Default             | 10 minutes
```

**Why?** Different failure types have different propagation times.

### 2. **30+ Domain Knowledge Patterns**

The system has 30+ Kubernetes-specific failure patterns:

```cypher
CASE
  // Resource exhaustion (HIGH confidence)
  WHEN e1.reason = 'OOMKilled' AND e2.reason IN ['BackOff', 'Failed', 'Killing']
    THEN 0.95
  WHEN e1.reason = 'OOMKilled' AND e2.reason = 'Evicted'
    THEN 0.90
  WHEN e1.reason = 'MemoryPressure' AND e2.reason IN ['OOMKilled', 'Evicted']
    THEN 0.88

  // Image/registry issues
  WHEN e1.reason CONTAINS 'ImagePull' AND e2.reason IN ['Failed', 'BackOff']
    THEN 0.90
  WHEN e1.reason = 'ImagePullBackOff' AND e2.reason = 'Failed'
    THEN 0.92

  // Health check failures
  WHEN e1.reason = 'Unhealthy' AND e2.reason IN ['Killing', 'Failed', 'BackOff']
    THEN 0.88

  // Scheduling failures
  WHEN e1.reason = 'FailedScheduling' AND e2.reason IN ['Pending', 'Failed']
    THEN 0.90

  // Volume/mount issues
  WHEN e1.reason = 'FailedMount' AND e2.reason IN ['Failed', 'ContainerCreating']
    THEN 0.88

  // Network failures
  WHEN e1.reason = 'NetworkNotReady' AND e2.reason IN ['Failed', 'Pending']
    THEN 0.85

  // ... 20+ more patterns ...

  // Generic fallback
  ELSE 0.30
END as domain_score
```

### 3. **Service Topology Integration**

Uses existing topology relationships to boost confidence:

```cypher
// Check if events are on topologically related resources
OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)

// Distance score based on topology
CASE
  WHEN r1.name = r2.name                          THEN 0.95  // Same resource
  WHEN topology_path AND length(path) = 1         THEN 0.85  // Direct connection
  WHEN topology_path AND length(path) = 2         THEN 0.70  // 2-hop connection
  WHEN topology_path AND length(path) = 3         THEN 0.55  // 3-hop connection
  WHEN r1.ns = r2.ns AND r1.kind = r2.kind        THEN 0.40  // Same namespace/kind
  ELSE 0.20                                                  // Unrelated
END as distance_score
```

### 4. **Multi-Dimensional Confidence Scoring**

Final confidence is a weighted combination:

```
confidence = (0.4 × temporal_score) +    // How close in time
             (0.3 × distance_score) +     // Topology distance
             (0.3 × domain_score)         // K8s domain patterns

Where:
- temporal_score: Linear decay over 5 minutes (1.0 → 0.1)
- distance_score: Based on topology path length
- domain_score: From 30+ K8s patterns
```

### 5. **Top-5 Filtering**

For each event, keep only the **top 5 most likely causes**:

```
Event: "nginx-pod Failed"
    ← Cause 1: OOMKilled (confidence: 0.95)
    ← Cause 2: DiskPressure (confidence: 0.85)
    ← Cause 3: NetworkNotReady (confidence: 0.73)
    ← Cause 4: Unhealthy (confidence: 0.68)
    ← Cause 5: ConfigMapNotFound (confidence: 0.52)
    ✗ Cause 6-10: Filtered out (lower confidence)
```

**Why?** Prevents noise and focuses on most likely causes.

---

## 🏗️ How Topology Relationships Are Created

### Created During Event Ingestion

When events are ingested from Kubernetes, the system:

1. **Extracts resource metadata** from K8s events
2. **Creates/updates Resource nodes**
3. **Creates topology relationships** based on K8s ownership/selectors

**Example Ingestion Flow:**
```
K8s Event: "Pod nginx-abc Failed"
    ↓
1. Create/Update Episodic node (event)
2. Create/Update Resource node (nginx-abc pod)
3. Create ABOUT relationship: (Episodic)-[:ABOUT]->(Resource)
4. Create topology relationships:
   - (Service nginx)-[:SELECTS]->(Pod nginx-abc)     // From service selector
   - (Pod nginx-abc)-[:RUNS_ON]->(Node node-1)       // From pod.spec.nodeName
   - (Deployment nginx)-[:CONTROLS]->(ReplicaSet nginx-rs)  // From owner refs
```

**Where this happens:**
- In your **event ingestion pipeline** (Kafka consumer, webhook handler, etc.)
- **Before** events reach Neo4j
- **Automatically** as part of data ingestion

---

## 🔄 When to Build Causality

### Option 1: **On-Demand** (Current System)

**Use When:**
- New events have been ingested
- Want to analyze specific time period
- Testing/debugging causality
- After fixing bugs in causality logic

**Command:**
```bash
curl -X POST http://localhost:8082/api/v1/rca/build-causality/loc-01
```

### Option 2: **Scheduled** (Recommended for Production)

**Setup a cron job:**
```bash
# Every 15 minutes
*/15 * * * * curl -X POST http://localhost:8082/api/v1/rca/build-causality/loc-01?time_range_hours=1

# Once per hour
0 * * * * curl -X POST http://localhost:8082/api/v1/rca/build-causality/loc-01?time_range_hours=2
```

### Option 3: **Streaming** (Future Enhancement)

Build causality in real-time as events arrive:

```python
# Pseudo-code for future enhancement
@kafka_consumer.on_event_batch
async def on_events(events):
    # Ingest events to Neo4j
    await ingest_events(events)

    # Build causality for last 15 minutes
    await build_causality(
        client_id=events[0].client_id,
        time_range_hours=0.25  # 15 minutes
    )
```

---

## 🎯 Current State of Your System

### What You Have:

✅ **Topology relationships**: Created during ingestion
- `Service -[SELECTS]-> Pod`
- `Pod -[RUNS_ON]-> Node`
- `Deployment -[CONTROLS]-> ReplicaSet`

✅ **Causality API**: On-demand relationship builder
- Endpoint: `POST /api/v1/rca/build-causality/{client_id}`
- Enhanced KGroot algorithm
- 30+ K8s domain patterns
- Multi-dimensional confidence scoring

❓ **Causality Relationships**: Need to be built on-demand
- **Why found 0 root causes for loc-01**: Causality relationships not built yet!

---

## 🚀 How to Fix "0 Root Causes" Issue

### Step 1: Build Causality for loc-01

```bash
# On your server
curl -X POST "http://localhost:8082/api/v1/rca/build-causality/loc-01?time_range_hours=24"
```

**Expected output:**
```json
{
  "events_analyzed": 1529,
  "relationships_created_or_updated": 847,
  "avg_confidence": 0.652,
  "message": "Successfully built 847 POTENTIAL_CAUSE relationships"
}
```

### Step 2: Verify Relationships Were Created

```bash
# Check Neo4j
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA "
MATCH (e1:Episodic {client_id: 'loc-01'})-[r:POTENTIAL_CAUSE]->(e2:Episodic)
RETURN count(r) as relationship_count,
       round(avg(r.confidence) * 1000.0) / 1000.0 as avg_confidence
"
```

### Step 3: Test RCA Again

```bash
# Try RCA on new AI SRE platform
curl -X POST http://localhost:8084/api/v1/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find root causes for failures",
    "tenant_id": "loc-01",
    "time_window_hours": 24
  }' | jq .
```

**Now you should see:**
```json
{
  "synthesis": {
    "summary": "Found 12 potential root causes",
    "root_causes": [
      {
        "reason": "DNS lookup failed",
        "confidence": 0.88
      },
      ...
    ]
  }
}
```

---

## 🎓 Add Causality Builder to New AI SRE Platform

Want to add the causality builder API to the **new AI SRE Platform (port 8084)**?

I can add it as a new endpoint:

```python
# New endpoint in AI SRE Platform
@app.post("/api/v1/build-causality/{client_id}")
async def build_causality(
    client_id: str,
    time_range_hours: int = 24,
    min_confidence: float = 0.3
):
    """
    Build POTENTIAL_CAUSE relationships using KGroot enhanced algorithm
    """
    # Use existing orchestrator's Neo4j service
    result = await orchestrator.neo4j.build_causality(
        client_id=client_id,
        time_range_hours=time_range_hours,
        min_confidence=min_confidence
    )
    return result
```

**Benefits:**
- ✅ One-stop API (investigation + causality building)
- ✅ Token budget tracking for causality building
- ✅ GraphRAG-ready after building

---

## 📊 Summary Table

| Feature | Topology (SELECTS, etc.) | Causality (POTENTIAL_CAUSE) |
|---------|-------------------------|----------------------------|
| **When Created** | During event ingestion | On-demand via API |
| **How** | From K8s metadata | KGroot algorithm |
| **Confidence** | N/A (structural) | 0.0-1.0 (computed) |
| **Used For** | Distance scoring | Root cause analysis |
| **Required For RCA** | Optional (boosts confidence) | **Required!** |
| **Auto-Created** | ✅ Yes | ❌ No (manual trigger) |

---

## 🔧 Next Steps

1. **Build causality for loc-01**:
   ```bash
   curl -X POST http://localhost:8082/api/v1/rca/build-causality/loc-01
   ```

2. **Set up automated causality building** (cron job):
   ```bash
   # Add to crontab
   */15 * * * * curl -X POST http://localhost:8082/api/v1/rca/build-causality/loc-01?time_range_hours=1
   ```

3. **Test RCA with real causality data**:
   ```bash
   curl -X POST http://localhost:8084/api/v1/investigate \
     -d '{"query": "Find DNS failures", "tenant_id": "loc-01"}'
   ```

4. **(Optional) Add causality builder to new AI SRE Platform**:
   - I can add the endpoint to port 8084
   - Integrates with orchestrator and token tracking
   - One-stop API for everything

---

## 🎉 Key Takeaways

1. **Topology**: Auto-created during ingestion ✅
2. **Causality**: Must be built on-demand ⚠️
3. **Why 0 results**: Causality not built yet for loc-01
4. **Solution**: Run build-causality API endpoint
5. **Future**: Set up scheduled causality building

**Want me to add the causality builder API to the new AI SRE Platform (port 8084)?**
