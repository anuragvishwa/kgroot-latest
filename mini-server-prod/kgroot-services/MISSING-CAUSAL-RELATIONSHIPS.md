# Missing POTENTIAL_CAUSE Relationships - Diagnosis & Fix

## Problem

Your Neo4j queries return `null` for all confidence scores and causes because **`:POTENTIAL_CAUSE` relationships don't exist** in your database.

### What You Have
- ✅ Events stored in Neo4j (`:Episodic` nodes)
- ✅ Resources stored (`:Resource` nodes)
- ✅ `:ABOUT` relationships linking events to resources
- ❌ **No `:POTENTIAL_CAUSE` relationships** linking events to their causes

### Why This Happens

**The code exists but doesn't run automatically:**

1. **EventGraphBuilder** ([event_graph_builder.py](core/event_graph_builder.py)) - Creates causal relationships in-memory
2. **RCAOrchestrator** ([rca_orchestrator.py](rca_orchestrator.py)) - Uses the graph builder
3. **BUT**: Neither service writes these relationships to Neo4j automatically
4. **Result**: The FPG (Fault Propagation Graph) exists only in Python memory during RCA queries

**Your current architecture:**
```
Kafka Events → Neo4j (Episodic + ABOUT) → RCA API reads events
                   ↓
            (POTENTIAL_CAUSE relationships MISSING!)
```

**What should happen:**
```
Kafka Events → Neo4j (Episodic + ABOUT)
                   ↓
            Graph Builder Service → Creates POTENTIAL_CAUSE relationships
                   ↓
            RCA API reads events WITH causal relationships
```

---

## Solution Options

### Option 1: Add Background Job to Create Relationships (Recommended)

Create a background service that periodically:
1. Reads recent events from Neo4j
2. Runs EventGraphBuilder to find causal relationships
3. Writes POTENTIAL_CAUSE relationships back to Neo4j

**Pros:**
- Precomputed relationships (faster RCA queries)
- Persistent causal graph
- Can analyze long-term patterns

**Cons:**
- Requires additional service/cron job
- More infrastructure complexity

### Option 2: Compute On-Demand During RCA

Modify RCA API to:
1. Read events from Neo4j
2. Compute POTENTIAL_CAUSE relationships in-memory
3. Return results (without storing relationships)

**Pros:**
- No additional service needed
- Always up-to-date causality
- Simpler deployment

**Cons:**
- Slower RCA queries (computes every time)
- No historical causal analysis
- Doesn't scale well with large event volumes

### Option 3: Quick Fix - Manual Relationship Creation

Run a one-time script to create POTENTIAL_CAUSE relationships for recent events.

**Pros:**
- Immediate fix for testing
- No code changes needed

**Cons:**
- Not automated (manual re-runs needed)
- Only fixes historical data

---

## Quick Fix: Create Relationships Manually

### Step 1: Check Current State

```cypher
// Check if ANY POTENTIAL_CAUSE relationships exist
MATCH ()-[pc:POTENTIAL_CAUSE]->()
RETURN count(pc) as total_relationships
```

Expected: `0` (confirmed from your null results)

### Step 2: Create Basic Causal Relationships

**RECOMMENDED:** Use the complete script file: **[CREATE-CAUSAL-RELATIONSHIPS.cypher](CREATE-CAUSAL-RELATIONSHIPS.cypher)**

That file has the full working script with all steps. Here's the main query (fixed - no `exp()` function):

```cypher
// Create causal relationships for events in last 24 hours
MATCH (e1:Episodic {client_id: 'ab-01'})
WHERE e1.event_time > datetime() - duration({hours: 24})

MATCH (e2:Episodic {client_id: 'ab-01'})
WHERE e2.event_time > e1.event_time
  AND e2.event_time < e1.event_time + duration({minutes: 10})

// Get resources
OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource)
OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource)

// Calculate time difference
WITH e1, e2, r1, r2,
     duration.between(e1.event_time, e2.event_time).seconds as time_diff_seconds

// Domain score (Kubernetes causality rules)
WITH e1, e2, r1, r2, time_diff_seconds,
     CASE
       WHEN e1.reason = 'OOMKilled' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.95
       WHEN e1.reason CONTAINS 'ImagePull' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.90
       WHEN e1.reason = 'Unhealthy' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.80
       WHEN e1.reason = 'Failed' AND e2.reason = 'BackOff' THEN 0.85
       WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.65
       ELSE 0.30
     END as domain_score

// Temporal score (linear decay)
WITH e1, e2, r1, r2, time_diff_seconds, domain_score,
     CASE
       WHEN time_diff_seconds <= 0 THEN 0.0
       WHEN time_diff_seconds >= 300 THEN 0.1
       ELSE 1.0 - (toFloat(time_diff_seconds) / 300.0) * 0.9
     END as temporal_score

// Distance score (graph proximity)
WITH e1, e2, time_diff_seconds, domain_score, temporal_score,
     CASE
       WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.95
       WHEN r1.ns = r2.ns AND r1.kind = r2.kind AND r1.ns IS NOT NULL THEN 0.60
       ELSE 0.20
     END as distance_score

// Overall confidence: 40% temporal + 30% distance + 30% domain
WITH e1, e2, temporal_score, distance_score, domain_score, time_diff_seconds,
     (0.4 * temporal_score + 0.3 * distance_score + 0.3 * domain_score) as confidence

WHERE confidence > 0.3

// Create the relationship
MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
SET pc.confidence = round(confidence * 1000.0) / 1000.0,
    pc.temporal_score = round(temporal_score * 1000.0) / 1000.0,
    pc.distance_score = round(distance_score * 1000.0) / 1000.0,
    pc.domain_score = round(domain_score * 1000.0) / 1000.0,
    pc.time_gap_seconds = time_diff_seconds,
    pc.created_at = datetime()

RETURN count(*) as relationships_created
```

### Step 3: Verify Relationships Created

```cypher
// Check what was created
MATCH (e1:Episodic)-[pc:POTENTIAL_CAUSE]->(e2:Episodic)
WHERE e1.client_id = 'ab-01'
RETURN
  e1.reason as cause,
  e2.reason as effect,
  pc.confidence as confidence,
  pc.temporal_score as temporal,
  pc.domain_score as domain,
  duration.between(e1.event_time, e2.event_time).seconds as time_gap_seconds
ORDER BY pc.confidence DESC
LIMIT 10
```

### Step 4: Test RCA Query Again

Now re-run your original query:
```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 60})
  AND e.client_id = 'ab-01'
  AND e.severity = 'WARNING'

OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)

RETURN
  e.reason as failure_reason,
  e.message as failure_message,
  collect({
    cause_reason: cause.reason,
    cause_message: cause.message,
    confidence: pc.confidence,
    temporal_score: pc.temporal_score,
    distance_score: pc.distance_score,
    domain_score: pc.domain_score
  }) as root_causes
ORDER BY e.event_time DESC
LIMIT 10
```

**Expected result:** Now you should see confidence scores instead of nulls!

---

## Advanced: Create Relationships for All Event Types

```cypher
// Create comprehensive causal relationships with multiple patterns
MATCH (e1:Episodic {client_id: 'ab-01'})
WHERE e1.event_time > datetime() - duration({hours: 24})

MATCH (e2:Episodic {client_id: 'ab-01'})
WHERE e2.event_time > e1.event_time
  AND e2.event_time < e1.event_time + duration({minutes: 10})

// Get resources
OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource)
OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource)

WITH e1, e2, r1, r2,
     duration.between(e1.event_time, e2.event_time).seconds as time_diff

// Calculate domain score based on known causality patterns
WITH e1, e2, r1, r2, time_diff,
     CASE
       // High confidence patterns (K8s domain knowledge)
       WHEN e1.reason = 'OOMKilled' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.95
       WHEN e1.reason IN ['Failed', 'ErrImagePull'] AND e2.reason = 'BackOff' THEN 0.90
       WHEN e1.reason = 'Unhealthy' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.80
       WHEN e1.reason CONTAINS 'Pull' AND e2.reason = 'Failed' THEN 0.85
       WHEN e1.reason = 'FailedScheduling' AND e2.reason IN ['Pending', 'Failed'] THEN 0.75
       WHEN e1.reason = 'FailedMount' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.80

       // Medium confidence patterns (same resource)
       WHEN r1.name = r2.name AND e1.severity = 'WARNING' AND e2.severity = 'WARNING' THEN 0.70

       // Low confidence (temporal correlation only)
       WHEN r1.ns = r2.ns THEN 0.50  // Same namespace

       ELSE 0.40  // Weak correlation
     END as domain_score

// Temporal score (exponential decay, tau=60s)
WITH e1, e2, r1, r2, time_diff, domain_score,
     exp(-time_diff / 60.0) as temporal_score

// Distance score (based on resource proximity)
WITH e1, e2, time_diff, domain_score, temporal_score,
     CASE
       WHEN r1.name = r2.name THEN 0.9  // Same pod
       WHEN r1.ns = r2.ns AND r1.kind = r2.kind THEN 0.6  // Same namespace/kind
       WHEN r1.ns = r2.ns THEN 0.4  // Same namespace
       ELSE 0.2  // Different namespace
     END as distance_score

// Overall confidence (weighted combination)
WITH e1, e2, temporal_score, distance_score, domain_score,
     (0.4 * temporal_score + 0.3 * distance_score + 0.3 * domain_score) as confidence

WHERE confidence > 0.3  // Minimum threshold

// Create relationship
MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
SET pc.confidence = round(confidence * 100) / 100.0,
    pc.temporal_score = round(temporal_score * 100) / 100.0,
    pc.distance_score = round(distance_score * 100) / 100.0,
    pc.domain_score = round(domain_score * 100) / 100.0,
    pc.created_at = datetime()

RETURN count(*) as total_relationships_created
```

---

## Long-Term Fix: Automated Graph Builder Service

You need to create a background service that runs periodically. Here's the architecture:

### Service: `graph-builder-service`

**Location:** `mini-server-prod/kgroot-services/services/graph_builder_service.py`

**What it does:**
1. Runs every 5 minutes (configurable)
2. Fetches recent events from Neo4j (last 10 minutes)
3. Groups events by incident/time window
4. Runs EventGraphBuilder to compute POTENTIAL_CAUSE relationships
5. Writes relationships back to Neo4j with confidence scores

**Deployment:**
```yaml
# Add to client-light Helm chart
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kgroot-graph-builder
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: graph-builder
        image: your-registry/kgroot-services:latest
        command: ["python", "services/graph_builder_service.py"]
        env:
        - name: NEO4J_URI
          value: "bolt://neo4j:7687"
        - name: GRAPH_BUILDER_INTERVAL_SECONDS
          value: "300"  # 5 minutes
```

---

## Testing Your Fix

### Test 1: Verify Relationships Created
```cypher
MATCH ()-[pc:POTENTIAL_CAUSE]->()
RETURN count(pc) as total,
       avg(pc.confidence) as avg_confidence,
       min(pc.confidence) as min_confidence,
       max(pc.confidence) as max_confidence
```

Expected: `total > 0`, `avg_confidence ~0.6-0.8`

### Test 2: Check Specific Failure Pattern
```cypher
// Find BackOff events and their causes
MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(effect:Episodic {reason: 'BackOff'})
RETURN cause.reason, effect.reason, pc.confidence
ORDER BY pc.confidence DESC
LIMIT 10
```

Expected: See causes like OOMKilled, Failed, Unhealthy → BackOff

### Test 3: Full RCA Query
Run the Quick Start query from [RCA-ANALYSIS-QUERIES.md](RCA-ANALYSIS-QUERIES.md) and verify you get confidence scores.

---

## Summary

**Current Issue:**
- EventGraphBuilder exists but doesn't write to Neo4j
- POTENTIAL_CAUSE relationships are never created
- RCA queries return null for all confidence scores

**Immediate Fix:**
- Run the Cypher script above to create relationships manually
- This will make your RCA queries work immediately

**Long-Term Fix:**
- Create graph-builder background service
- Automates relationship creation
- Keeps causal graph up-to-date

**Next Steps:**
1. Run Step 2 Cypher script to create relationships
2. Test with Step 4 query
3. Check RCA-ANALYSIS-QUERIES.md to see all advanced queries now working
4. Plan deployment of automated graph-builder service

---

## Related Files

- [event_graph_builder.py](core/event_graph_builder.py) - Causal relationship logic
- [RCA-ANALYSIS-QUERIES.md](RCA-ANALYSIS-QUERIES.md) - Queries that need POTENTIAL_CAUSE
- [rca_orchestrator.py](rca_orchestrator.py) - Orchestrates RCA but doesn't persist to Neo4j
- [TEST-NEO4J-QUERIES.md](TEST-NEO4J-QUERIES.md) - Verification queries
