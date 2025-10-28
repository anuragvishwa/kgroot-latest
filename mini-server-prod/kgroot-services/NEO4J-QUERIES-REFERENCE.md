# Neo4j Queries Reference Guide

> Complete reference of all Neo4j queries used in KGroot with explanations, parameters, and analysis.

---

## Table of Contents

- [RCA Queries](#rca-queries)
- [Pattern Storage Queries](#pattern-storage-queries)
- [Pattern Retrieval Queries](#pattern-retrieval-queries)
- [Topology Queries](#topology-queries)
- [Schema & Index Queries](#schema--index-queries)
- [Query Analysis & Performance](#query-analysis--performance)

---

## RCA Queries

### Query 0: Quick Data Verification Queries

**Purpose:** Verify data ingestion and check event types before running full RCA.

#### 0.1 Check Event Type Distribution
```cypher
// Count events by type for a time window (last 2 hours)
MATCH (e:Episodic {client_id: 'ab-01'})
WHERE e.event_time > datetime() - duration({hours: 2})
RETURN e.etype, count(*) as count
ORDER BY count DESC
```

**Parameters:**
- `client_id`: Your cluster ID (e.g., `'ab-01'`)
- Time window: Last 2 hours using `datetime() - duration({hours: 2})`

**Real Output from Production:**
```
| etype      | count |
|------------|-------|
| k8s.log    | 737   |
| k8s.event  | 515   |
```

**Analysis:** Healthy ratio is 40-60% events, 40-60% logs. If 100% logs, check event ingestion.

**Time Window Variations:**
```cypher
// Last 30 minutes (RCA window)
WHERE e.event_time > datetime() - duration({minutes: 30})

// Last 24 hours
WHERE e.event_time > datetime() - duration({days: 1})

// Last week
WHERE e.event_time > datetime() - duration({days: 7})
```

---

#### 0.2 Check Recent K8s Events (Last 10 Minutes)
```cypher
// Get only K8s events (exclude logs) - Last 10 minutes
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 10})
  AND e.client_id = 'ab-01'
  AND e.etype <> 'k8s.log'  // Exclude logs, show only events
RETURN e.etype, e.reason, e.message, e.severity
ORDER BY e.event_time DESC
LIMIT 20
```

**Parameters:**
- `client_id`: `'ab-01'` (replace with your cluster ID)
- Time window: Last 10 minutes using `datetime() - duration({minutes: 10})`

**Real Output from Production (ab-01 cluster):**
```
| etype      | reason           | message                                                                           | severity |
|------------|------------------|-----------------------------------------------------------------------------------|----------|
| k8s.event  | Completed        | Job completed                                                                     | INFO     |
| k8s.event  | Started          | Started container heartbeat                                                       | INFO     |
| k8s.event  | Pulled           | Container image "edenhill/kcat:1.7.1" already present on machine                  | INFO     |
| k8s.event  | Created          | Created container: heartbeat                                                      | INFO     |
| k8s.event  | Scheduled        | Successfully assigned observability/kg-rca-agent-heartbeat-29360760-f99zw to node01 | INFO     |
| k8s.event  | SuccessfulCreate | Created pod: kg-rca-agent-kg-rca-agent-heartbeat-29360760-f99zw                  | INFO     |
| k8s.event  | Pulled           | Successfully pulled image "polinux/stress" in 241ms (241ms including waiting)     | INFO     |
```

**Use Case:** Verify events are flowing. All INFO means system is healthy. Look for ERROR/WARNING for RCA.

**Time Window Variations:**
```cypher
// Last 5 minutes (very recent activity)
WHERE e.event_time > datetime() - duration({minutes: 5})

// Last 30 minutes (standard RCA window)
WHERE e.event_time > datetime() - duration({minutes: 30})

// Last hour (historical view)
WHERE e.event_time > datetime() - duration({hours: 1})
```

---

#### 0.3 Filter High-Signal Events for RCA (Production-Ready)

**Four approaches from simple to comprehensive:**

##### **Option A: Simple Severity-Based Filter ⭐ RECOMMENDED**
```cypher
// Get all non-INFO events - Last 30 minutes
// This catches ALL failure types dynamically (no hardcoded list)
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND (
    // Include all K8s events that are not INFO (catches everything!)
    (e.etype = 'k8s.event' AND e.severity <> 'INFO' AND e.severity <> '')
    OR
    // Include ERROR/WARNING/FATAL logs
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 500
```

**Why This Works Best:**
- ✅ **Dynamic** - Catches ALL failure types (OOMKilled, BackOff, Failed, CrashLoopBackOff, ImagePullBackOff, etc.)
- ✅ **Future-proof** - Works with new Kubernetes event types without code changes
- ✅ **Simple** - No maintenance of hardcoded failure lists
- ✅ **Production-tested** - Kubernetes severity field is standardized
- ✅ **Fast** - Simple condition, uses indexes

---

##### **Option B: Reason-Based Pattern Matching**
```cypher
// Filter by failure patterns in reason field - Last 30 minutes
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND (
    // Pattern match: Any reason containing failure keywords (case-insensitive)
    (e.etype = 'k8s.event' AND (
      toLower(e.reason) CONTAINS 'fail' OR
      toLower(e.reason) CONTAINS 'error' OR
      toLower(e.reason) CONTAINS 'kill' OR
      toLower(e.reason) CONTAINS 'crash' OR
      toLower(e.reason) CONTAINS 'backoff' OR
      toLower(e.reason) CONTAINS 'evict' OR
      toLower(e.reason) CONTAINS 'unhealthy' OR
      toLower(e.reason) CONTAINS 'timeout' OR
      toLower(e.reason) CONTAINS 'unknown'
    ))
    OR
    // Include ERROR/WARNING logs
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 500
```

**Why This Works:**
- ✅ **Pattern-based** - Matches failure keywords in reason field
- ✅ **Comprehensive** - Catches variations like "Failed", "FailedScheduling", "FailedMount"
- ✅ **Flexible** - Works even if severity is missing or incorrect
- ⚠️ **Slower** - Pattern matching is more expensive than exact match

**Matches These Patterns:**
- `OOMKilled` → contains "kill"
- `Failed`, `FailedScheduling`, `FailedMount`, `FailedAttachVolume` → contains "fail"
- `CrashLoopBackOff` → contains "crash"
- `BackOff`, `ImagePullBackOff` → contains "backoff"
- `Evicted` → contains "evict"
- `Unhealthy` → contains "unhealthy"
- `Timeout` → contains "timeout"
- `ContainerStatusUnknown` → contains "unknown"

---

##### **Option C: Combined Severity + Reason + Message (Most Comprehensive)**
```cypher
// Multi-factor filter - catches everything - Last 30 minutes
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND (
    // Factor 1: Severity-based (primary filter)
    (e.etype = 'k8s.event' AND e.severity IN ['WARNING', 'ERROR', 'CRITICAL'])
    OR
    // Factor 2: Reason-based pattern matching (catches missed cases)
    (e.etype = 'k8s.event' AND (
      toLower(e.reason) CONTAINS 'fail' OR
      toLower(e.reason) CONTAINS 'error' OR
      toLower(e.reason) CONTAINS 'kill' OR
      toLower(e.reason) CONTAINS 'crash' OR
      toLower(e.reason) CONTAINS 'backoff' OR
      toLower(e.reason) CONTAINS 'evict' OR
      toLower(e.reason) CONTAINS 'unknown'
    ))
    OR
    // Factor 3: Message-based (catches edge cases)
    (e.etype = 'k8s.event' AND (
      toLower(e.message) CONTAINS 'error' OR
      toLower(e.message) CONTAINS 'failed' OR
      toLower(e.message) CONTAINS 'crash' OR
      toLower(e.message) CONTAINS 'timeout'
    ))
    OR
    // Factor 4: Error logs
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 500
```

**Why This is Most Comprehensive:**
- ✅ **Triple redundancy** - Severity, reason, and message patterns
- ✅ **Catches everything** - Even misconfigured or unlabeled events
- ✅ **No false negatives** - Better to get extra events than miss critical ones
- ⚠️ **Slowest** - Multiple pattern matches across multiple fields

---

##### **Option D: Inverse Filter - Exclude Normal Operations (Whitelist Approach)**
```cypher
// Exclude known-good events instead of listing bad ones - Last 30 minutes
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND e.etype = 'k8s.event'
  AND NOT (
    // Exclude normal operations (whitelist approach)
    e.reason IN [
      'Scheduled', 'Pulled', 'Created', 'Started', 'Killing',
      'SuccessfulCreate', 'SuccessfulDelete', 'ScalingReplicaSet',
      'NoPods', 'Completed', 'LeaderElection', 'NodeReady',
      'NodeHasSufficientMemory', 'NodeHasSufficientDisk', 'RegisteredNode'
    ]
    AND e.severity = 'INFO'
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 500
```

**Why This Works:**
- ✅ **Whitelist approach** - Safer than blacklist (catches unknown failures)
- ✅ **Maintenance** - Update whitelist as you identify normal operations
- ⚠️ **Trade-off** - May include some low-signal events initially
- ✅ **Good for learning** - Helps identify what's normal in your environment

---

### 🎯 Production Recommendation

**For production environments, use Option A (Severity-Based):**

```cypher
MATCH (e:Episodic)
WHERE e.event_time > datetime() - duration({minutes: 30})
  AND e.client_id = 'ab-01'
  AND (
    (e.etype = 'k8s.event' AND e.severity <> 'INFO' AND e.severity <> '')
    OR
    (e.etype = 'k8s.log' AND e.reason IN ['LOG_ERROR', 'LOG_WARNING', 'LOG_FATAL'])
  )
RETURN e.etype, e.reason, e.message, e.severity, e.event_time
ORDER BY e.event_time DESC
LIMIT 500
```

**Why:**
- Simple and fast
- Dynamic - works with any Kubernetes failure
- Low maintenance
- Kubernetes severity field is standardized

**If you're missing events, add Option B (pattern matching) or Option C (comprehensive) as needed.**

---

### 📊 Expected Output (All Kubernetes Failure Types)

```
| etype      | reason                    | message                                              | severity | event_time                |
|------------|---------------------------|------------------------------------------------------|----------|---------------------------|
| k8s.event  | OOMKilled                 | Container exceeded memory limit                      | ERROR    | 2025-10-28T10:15:30.000Z |
| k8s.event  | CrashLoopBackOff          | Back-off restarting failed container                 | WARNING  | 2025-10-28T10:15:25.000Z |
| k8s.event  | FailedScheduling          | 0/3 nodes are available: insufficient memory         | WARNING  | 2025-10-28T10:15:20.000Z |
| k8s.event  | FailedMount               | Unable to mount volumes: timeout expired             | ERROR    | 2025-10-28T10:15:15.000Z |
| k8s.event  | ImagePullBackOff          | Back-off pulling image "app:v2.0"                    | WARNING  | 2025-10-28T10:15:10.000Z |
| k8s.event  | Unhealthy                 | Readiness probe failed: connection refused           | WARNING  | 2025-10-28T10:15:05.000Z |
| k8s.event  | FailedAttachVolume        | AttachVolume.Attach failed for volume "pvc-123"      | ERROR    | 2025-10-28T10:15:00.000Z |
| k8s.event  | FailedCreatePodSandBox    | Failed to create pod sandbox                         | WARNING  | 2025-10-28T10:14:55.000Z |
| k8s.log    | LOG_ERROR                 | Connection to database failed: timeout               | ERROR    | 2025-10-28T10:14:50.000Z |
| k8s.event  | BackOff                   | Back-off restarting failed pod                       | WARNING  | 2025-10-28T10:14:45.000Z |
| k8s.event  | Evicted                   | Pod evicted due to node pressure                     | WARNING  | 2025-10-28T10:14:40.000Z |
| k8s.event  | FailedKillPod             | Error killing pod                                    | ERROR    | 2025-10-28T10:14:35.000Z |
| k8s.event  | FailedPreStopHook         | PreStop hook failed                                  | WARNING  | 2025-10-28T10:14:30.000Z |
| k8s.event  | NetworkNotReady           | Network not ready: runtime network not ready         | WARNING  | 2025-10-28T10:14:25.000Z |
| k8s.event  | InspectFailed             | Failed to inspect image                              | ERROR    | 2025-10-28T10:14:20.000Z |
| k8s.event  | ErrImageNeverPull         | Container image pull policy is Never                 | WARNING  | 2025-10-28T10:14:15.000Z |
```

**This catches 50+ Kubernetes failure types including:**
- Memory: OOMKilled, OutOfMemory
- CPU: ThrottlingCgroup
- Disk: DiskPressure, OutOfDisk
- Network: NetworkNotReady, FailedCreatePodSandBox
- Images: ImagePullBackOff, ErrImagePull, InspectFailed
- Scheduling: FailedScheduling, Unschedulable
- Volumes: FailedMount, FailedAttachVolume, VolumeResizeFailed
- Probes: Unhealthy, ProbeError
- Lifecycle: BackOff, CrashLoopBackOff, FailedKillPod, FailedPreStopHook
- Eviction: Evicted, EvictionThresholdMet
- And many more!

**Note:** If this returns 0 results, your system is healthy! Try increasing the time window:
```cypher
// Last 2 hours
WHERE e.event_time > datetime() - duration({hours: 2})

// Last 24 hours (to find past failures)
WHERE e.event_time > datetime() - duration({days: 1})

// Last week (for pattern analysis)
WHERE e.event_time > datetime() - duration({days: 7})
```

---

### Query 1: Comprehensive RCA Event Retrieval

**Location:** `rca_api_neo4j.py:113-165`

**Purpose:** Fetch all events with their causal relationships, topology, and incidents for root cause analysis.

**Query:**

```cypher
// Get episodic events (events + logs) with context
MATCH (e:Episodic)
WHERE e.event_time > datetime($cutoff_time)
  AND e.client_id = $client_id

// OPTIONAL: Get related resource (may not exist yet)
OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)
WHERE r.ns = $namespace

// Get causes with confidence
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)

// Get topology
OPTIONAL MATCH (r)-[rel:SELECTS|RUNS_ON|CONTROLS]-(dep:Resource {client_id: $client_id})

// Get incidents
OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident {client_id: $client_id})

RETURN
    e.eid as eid,
    e.etype as etype,
    e.severity as severity,
    e.reason as reason,
    e.message as message,
    e.event_time as event_time,
    e.escalated as escalated,
    e.repeat_count as repeat_count,
    r.rid as resource_id,
    r.kind as kind,
    r.ns as ns,
    r.name as name,
    r.node as node,
    r.status_json as status,
    collect(DISTINCT {
        cause_id: cause.eid,
        reason: cause.reason,
        message: cause.message,
        confidence: pc.confidence,
        temporal: pc.temporal_score,
        distance: pc.distance_score,
        domain: pc.domain_score
    }) as causes,
    collect(DISTINCT {
        dep_id: dep.rid,
        dep_kind: dep.kind,
        dep_name: dep.name,
        rel_type: type(rel)
    }) as deps,
    collect(DISTINCT inc.resource_id) as incidents
ORDER BY e.event_time DESC
LIMIT 500
```

**Parameters:**
| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `$cutoff_time` | String (ISO DateTime) | Yes | Start of time window | `"2025-01-28T10:00:00Z"` |
| `$client_id` | String | Yes | Client/cluster identifier | `"prod-cluster-1"` |
| `$namespace` | String | No | Kubernetes namespace filter | `"default"` or `null` |

**Returns:**

- **Events**: List of episodic events (events + logs)
- **Causes**: Map of event_id → list of causal predecessors with confidence scores
- **Dependencies**: Service topology relationships for blast radius
- **Incidents**: Incident associations

**Analysis:**

1. **Query Pattern:**

   - Main MATCH on `:Episodic` nodes with time and client filters
   - 4x OPTIONAL MATCH for related data (resource, causes, topology, incidents)
   - Uses `collect(DISTINCT)` to aggregate relationships

2. **Performance Characteristics:**

   - **Index Usage**: Requires indexes on `(e.event_time, e.client_id)`
   - **Cardinality**: Typically 50-500 events per 30-minute window
   - **Complexity**: O(n) for events, O(n×k) for relationships (k=avg relationships per event)
   - **Execution Time**: 50-200ms typical, 500ms+ for large graphs

3. **Key Features:**

   - ✅ **Dynamic event types** - No hardcoded type mapping
   - ✅ **Multi-dimensional confidence** - Temporal, distance, domain scores
   - ✅ **Namespace isolation** - Optional filtering by namespace
   - ✅ **Service topology** - Includes SELECTS/RUNS_ON/CONTROLS relationships

4. **Optimization Tips:**

   ```cypher
   // Add index on event_time for faster filtering
   CREATE INDEX episodic_event_time IF NOT EXISTS
   FOR (e:Episodic) ON (e.event_time);

   // Add composite index for client_id + event_time
   CREATE INDEX episodic_client_time IF NOT EXISTS
   FOR (e:Episodic) ON (e.client_id, e.event_time);
   ```

5. **Common Issues:**
   - **Slow with no time filter**: Always include time window
   - **Large collect() result**: LIMIT 500 prevents excessive data
   - **OPTIONAL MATCH overhead**: Consider splitting query if topology not needed

**Example Usage:**

```python
cutoff_time = (datetime.utcnow() - timedelta(minutes=30)).isoformat()

context = await query_neo4j_for_rca(
    client_id="prod-cluster-1",
    time_window_minutes=30,
    namespace="default"
)

# Returns:
# {
#   'events': [Event(event_id='evt-123', etype='oom_kill', ...)],
#   'causes': {
#       'evt-123': [
#           {'cause_id': 'evt-100', 'confidence': 0.92,
#            'temporal': 0.95, 'distance': 0.88, 'domain': 0.93}
#       ]
#   },
#   'topology': {'pod/api-gateway-xyz': [...]},
#   'namespace': 'default',
#   'time_window': 30
# }
```

---

## Pattern Storage Queries

### Query 2: Create Pattern Schema

**Location:** `utils/neo4j_pattern_store.py:41-68`

**Purpose:** Initialize schema with constraints and indexes for pattern storage.

**Queries:**

#### 2.1 FailurePattern Unique Constraint

```cypher
CREATE CONSTRAINT failure_pattern_id IF NOT EXISTS
FOR (fp:FailurePattern) REQUIRE fp.pattern_id IS UNIQUE
```

**Purpose:** Ensure each pattern has unique identifier
**Analysis:** Prevents duplicate patterns, enables fast lookups via hash index

#### 2.2 AbstractEvent Unique Constraint

```cypher
CREATE CONSTRAINT abstract_event_signature IF NOT EXISTS
FOR (ae:AbstractEvent) REQUIRE ae.signature IS UNIQUE
```

**Purpose:** Ensure each abstract event type has unique signature
**Analysis:** Signature is hash of (event_type, service_pattern, severity)

#### 2.3 Root Cause Index

```cypher
CREATE INDEX failure_pattern_root_cause IF NOT EXISTS
FOR (fp:FailurePattern) ON (fp.root_cause_type)
```

**Purpose:** Fast semantic search by root cause type
**Analysis:** Enables `MATCH (fp {root_cause_type: 'OOM_KILL'})` in O(log n)

#### 2.4 Frequency Index

```cypher
CREATE INDEX failure_pattern_frequency IF NOT EXISTS
FOR (fp:FailurePattern) ON (fp.frequency)
```

**Purpose:** Fast sorting by pattern frequency
**Analysis:** Used for `ORDER BY fp.frequency DESC` queries

**Performance Impact:**

- Constraint creation: 10-50ms per constraint
- Index creation: 50-500ms per index (depends on existing data)
- Query speedup: 10-100x for filtered queries

---

### Query 3: Store Failure Pattern

**Location:** `utils/neo4j_pattern_store.py:84-152`

**Purpose:** Store a learned failure pattern (FEKG) in Neo4j.

#### 3.1 Create/Update FailurePattern Node

```cypher
MERGE (fp:FailurePattern {pattern_id: $pattern_id})
SET fp.root_cause_type = $root_cause_type,
    fp.fault_type = $fault_type,
    fp.event_sequence = $event_sequence,
    fp.frequency = $frequency,
    fp.first_seen = datetime($first_seen),
    fp.last_seen = datetime($last_seen),
    fp.avg_resolution_time_seconds = $avg_resolution_time,
    fp.resolution_steps = $resolution_steps,
    fp.prevention_measures = $prevention_measures,
    fp.updated_at = datetime()
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `pattern_id` | String | Unique pattern hash | `"pattern-oom-restart-001"` |
| `root_cause_type` | String | Root cause classification | `"OOM_KILL"` |
| `fault_type` | String | General fault category | `"resource_exhaustion"` |
| `event_sequence` | List[String] | Ordered event signatures | `["evt_sig_1", "evt_sig_2"]` |
| `frequency` | Integer | Times pattern occurred | `42` |
| `first_seen` | String (ISO) | First occurrence | `"2025-01-01T10:00:00Z"` |
| `last_seen` | String (ISO) | Last occurrence | `"2025-01-28T15:30:00Z"` |
| `avg_resolution_time` | Float | Avg time to resolve (sec) | `300.0` |
| `resolution_steps` | List[String] | Known fix steps | `["Increase memory", "Restart pod"]` |
| `prevention_measures` | List[String] | Prevention actions | `["Add memory limits", "Enable HPA"]` |

**Analysis:**

- Uses `MERGE` for idempotency (safe to run multiple times)
- `datetime()` function converts ISO strings to Neo4j DateTime
- Arrays stored natively in Neo4j (no JSON serialization needed)
- Typical execution: 5-20ms per pattern

#### 3.2 Create AbstractEvent Nodes

```cypher
MERGE (ae:AbstractEvent {signature: $signature})
SET ae.event_type = $event_type,
    ae.service_pattern = $service_pattern,
    ae.severity = $severity,
    ae.metric_threshold_pattern = $metric_threshold_pattern,
    ae.occurrence_count = $occurrence_count
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `signature` | String | Event signature hash | `"sig_oom_apigw_critical"` |
| `event_type` | String | Event type enum | `"oom_kill"` |
| `service_pattern` | String | Service name pattern | `"api-*"` (supports wildcards) |
| `severity` | String | Severity level | `"critical"` |
| `metric_threshold_pattern` | String | Metric pattern | `"memory > 90%"` |
| `occurrence_count` | Integer | Times event in pattern | `3` |

**Analysis:**

- Abstract events are reusable across patterns
- `service_pattern` supports wildcards for generalization
- Signature uniqueness prevents duplicate abstract events

#### 3.3 Link Pattern to Events

```cypher
MATCH (fp:FailurePattern {pattern_id: $pattern_id})
MATCH (ae:AbstractEvent {signature: $signature})
MERGE (fp)-[:CONTAINS_EVENT]->(ae)
```

**Purpose:** Establish pattern-event containment relationship
**Analysis:**

- MERGE prevents duplicate relationships
- Execution: 2-5ms per relationship

#### 3.4 Create Causal Relationships

```cypher
MATCH (source:AbstractEvent {signature: $source})
MATCH (target:AbstractEvent {signature: $target})
MATCH (fp:FailurePattern {pattern_id: $pattern_id})
MERGE (source)-[r:CAUSES {pattern_id: $pattern_id}]->(target)
SET r.relation_type = $relation_type,
    r.confidence = $confidence
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `source` | String | Source event signature | `"sig_oom_kill"` |
| `target` | String | Target event signature | `"sig_pod_restart"` |
| `pattern_id` | String | Pattern identifier | `"pattern-001"` |
| `relation_type` | String | Relation type | `"causes"`, `"propagates_to"`, `"sequential"`, `"correlates_with"` |
| `confidence` | Float | Confidence (0-1) | `0.95` |

**Analysis:**

- Pattern-scoped relationships (allows same event pair in multiple patterns)
- Directed graph structure (source → target)
- Confidence score for ranking

**Full Transaction Example:**

```python
def store_pattern(fekg):
    with driver.session() as session:
        with session.begin_transaction() as tx:
            # 1. Create pattern node
            tx.run(create_pattern_query, pattern_params)

            # 2. Create abstract events (bulk)
            for event in fekg.abstract_events.values():
                tx.run(create_abstract_event_query, event_params)

            # 3. Link pattern to events (bulk)
            for signature in fekg.abstract_events.keys():
                tx.run(link_pattern_event_query, link_params)

            # 4. Create causal relationships (bulk)
            for source, target, data in fekg.graph.edges(data=True):
                tx.run(create_causality_query, causality_params)

            tx.commit()
```

**Performance:**

- Single pattern storage: 50-200ms (depends on event count)
- Bulk storage (10 patterns): 500ms-2s
- Network overhead: 10-30ms per query (reduce with batching)

---

## Pattern Retrieval Queries

### Query 4: Get Pattern by ID

**Location:** `utils/neo4j_pattern_store.py:172-188`

**Query:**

```cypher
MATCH (fp:FailurePattern {pattern_id: $pattern_id})
OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
OPTIONAL MATCH (ae1:AbstractEvent)-[r:CAUSES {pattern_id: $pattern_id}]->(ae2:AbstractEvent)
RETURN fp,
       collect(DISTINCT ae) as abstract_events,
       collect(DISTINCT [ae1.signature, r, ae2.signature]) as relations
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `pattern_id` | String | Pattern identifier | `"pattern-oom-restart-001"` |

**Returns:**

- `fp`: FailurePattern node with all properties
- `abstract_events`: List of AbstractEvent nodes
- `relations`: List of [source_sig, relationship, target_sig] triples

**Analysis:**

1. **Query Structure:**

   - Main MATCH on pattern_id (uses unique constraint index)
   - OPTIONAL MATCH for events (pattern may have 0 events initially)
   - OPTIONAL MATCH for causality with pattern_id filter

2. **Performance:**

   - Pattern lookup: O(1) via unique constraint
   - Event collection: O(n) where n = events in pattern (typically 3-10)
   - Relation collection: O(m) where m = edges (typically 2-15)
   - Total execution: 10-50ms

3. **Result Processing:**

   ```python
   record = result.single()

   pattern_data = dict(record['fp'])
   # {pattern_id, root_cause_type, frequency, resolution_steps, ...}

   events = [dict(ae) for ae in record['abstract_events'] if ae]
   # [{'signature': 'sig_1', 'event_type': 'oom_kill', ...}, ...]

   relations = record['relations']
   # [['sig_1', <Relationship>, 'sig_2'], ...]
   ```

**Example Usage:**

```python
pattern = pattern_store.get_pattern("pattern-oom-restart-001")

if pattern:
    print(f"Root cause: {pattern.root_cause_type}")
    print(f"Frequency: {pattern.frequency} occurrences")
    print(f"Resolution: {pattern.resolution_steps}")
    print(f"Events: {len(pattern.abstract_events)}")
```

---

### Query 5: Get All Patterns

**Location:** `utils/neo4j_pattern_store.py:203-220`

**Query:**

```cypher
MATCH (fp:FailurePattern)
OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
OPTIONAL MATCH (ae1:AbstractEvent)-[r:CAUSES]->(ae2:AbstractEvent)
WHERE r.pattern_id = fp.pattern_id
RETURN fp,
       collect(DISTINCT ae) as abstract_events,
       collect(DISTINCT [ae1.signature, r, ae2.signature]) as relations
ORDER BY fp.frequency DESC
```

**Returns:** All patterns sorted by frequency (most common first)

**Analysis:**

1. **Query Pattern:**

   - Full table scan on `:FailurePattern` (acceptable for small pattern libraries)
   - Collects all events and relations per pattern
   - Orders by frequency DESC (most common patterns first)

2. **Performance:**

   - Pattern count: Typically 10-100 patterns
   - Execution time: 100-500ms for 50 patterns, 1-3s for 500 patterns
   - Memory usage: ~1-5MB for typical pattern library

3. **Optimization for Large Libraries:**

   ```cypher
   // Add LIMIT for pagination
   MATCH (fp:FailurePattern)
   OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
   OPTIONAL MATCH (ae1:AbstractEvent)-[r:CAUSES]->(ae2:AbstractEvent)
   WHERE r.pattern_id = fp.pattern_id
   RETURN fp, collect(DISTINCT ae) as abstract_events,
          collect(DISTINCT [ae1.signature, r, ae2.signature]) as relations
   ORDER BY fp.frequency DESC
   SKIP $skip LIMIT $limit
   ```

4. **Use Case:**
   - Load pattern library at startup
   - Periodic refresh (every 5-10 minutes)
   - Cache in memory for fast pattern matching

**Example Usage:**

```python
patterns = pattern_store.get_all_patterns()

print(f"Loaded {len(patterns)} patterns")
for i, pattern in enumerate(patterns[:10], 1):
    print(f"{i}. {pattern.root_cause_type}: "
          f"{pattern.frequency}x, "
          f"{len(pattern.abstract_events)} events")

# Output:
# Loaded 47 patterns
# 1. OOM_KILL: 127x, 4 events
# 2. CONFIG_CHANGE: 89x, 3 events
# 3. DEPLOYMENT: 76x, 5 events
# ...
```

---

### Query 6: Search Patterns by Root Cause

**Location:** `utils/neo4j_pattern_store.py:247-265`

**Query:**

```cypher
MATCH (fp:FailurePattern {root_cause_type: $root_cause_type})
OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
OPTIONAL MATCH (ae1:AbstractEvent)-[r:CAUSES]->(ae2:AbstractEvent)
WHERE r.pattern_id = fp.pattern_id
RETURN fp,
       collect(DISTINCT ae) as abstract_events,
       collect(DISTINCT [ae1.signature, r, ae2.signature]) as relations
ORDER BY fp.frequency DESC
LIMIT $limit
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `root_cause_type` | String | Root cause classification | `"OOM_KILL"` |
| `limit` | Integer | Max results | `10` |

**Analysis:**

1. **Index Usage:**

   - Uses `failure_pattern_root_cause` index
   - Lookup complexity: O(log n) → O(k) where k = matching patterns
   - Typical k: 5-20 patterns per root cause type

2. **Common Root Cause Types:**

   - `OOM_KILL` - Out of memory kills
   - `CONFIG_CHANGE` - Configuration changes
   - `DEPLOYMENT` - Deployment-related failures
   - `RESOURCE_EXHAUSTION` - CPU/Memory/Disk exhaustion
   - `NETWORK_ERROR` - Network connectivity issues
   - `HEALTH_CHECK_FAILED` - Health check failures
   - `NODE_FAILURE` - Node-level issues
   - `STORAGE_ISSUE` - PVC, disk, volume problems

3. **Performance:**
   - Execution: 20-100ms (depends on result count)
   - Result size: Typically 3-15 patterns
   - Cache candidates: Cache results for 5-10 minutes

**Example Usage:**

```python
# Find all OOM-related patterns
oom_patterns = pattern_store.search_patterns_by_root_cause(
    root_cause_type="OOM_KILL",
    limit=10
)

print(f"Found {len(oom_patterns)} OOM patterns")
for pattern in oom_patterns:
    print(f"\nPattern: {pattern.pattern_id}")
    print(f"  Frequency: {pattern.frequency}")
    print(f"  Sequence: {' → '.join(pattern.event_sequence)}")
    print(f"  Resolution: {pattern.resolution_steps}")
    print(f"  Avg fix time: {pattern.avg_resolution_time_seconds}s")

# Output:
# Found 3 OOM patterns
#
# Pattern: pattern-oom-restart-001
#   Frequency: 47
#   Sequence: memory_high → oom_kill → pod_restart → service_down
#   Resolution: ['Increase memory limits', 'Add memory requests', 'Review resource usage']
#   Avg fix time: 180s
```

---

### Query 7: Update Pattern Frequency

**Location:** `utils/neo4j_pattern_store.py:270-276`

**Query:**

```cypher
MATCH (fp:FailurePattern {pattern_id: $pattern_id})
SET fp.frequency = fp.frequency + 1,
    fp.last_seen = datetime(),
    fp.updated_at = datetime()
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `pattern_id` | String | Pattern identifier | `"pattern-oom-restart-001"` |

**Purpose:** Increment frequency when pattern matched (reinforcement learning)

**Analysis:**

1. **Atomic Operation:**

   - Uses Neo4j's atomic increment (`frequency = frequency + 1`)
   - No race conditions (safe for concurrent updates)
   - Transaction isolation level: READ_COMMITTED

2. **Performance:**

   - Execution: 2-10ms
   - Index lookup: O(1) via unique constraint
   - SET operation: O(1)

3. **Update Frequency:**

   - Called after every pattern match
   - Typical rate: 10-50 updates/minute
   - No performance bottleneck

4. **Timestamp Tracking:**
   - `last_seen`: Last time pattern matched (for recency)
   - `updated_at`: Last modification time (for cache invalidation)

**Example Usage:**

```python
# After matching pattern to online failure
pattern_match = matcher.find_similar_patterns(fpg, pattern_library, top_k=1)[0]

if pattern_match.similarity_score > 0.8:
    # Pattern matched with high confidence
    pattern_store.update_pattern_frequency(pattern_match.pattern.pattern_id)
    logger.info(f"Matched pattern {pattern_match.pattern.pattern_id}, "
                f"new frequency: {pattern_match.pattern.frequency + 1}")
```

---

### Query 8: Pattern Library Statistics

**Location:** `utils/neo4j_pattern_store.py:344-359`

**Query:**

```cypher
MATCH (fp:FailurePattern)
OPTIONAL MATCH (fp)-[:CONTAINS_EVENT]->(ae:AbstractEvent)
RETURN count(DISTINCT fp) as pattern_count,
       count(DISTINCT ae) as event_type_count,
       sum(fp.frequency) as total_matches,
       collect(DISTINCT fp.root_cause_type) as root_cause_types
```

**Returns:**
| Field | Type | Description |
|-------|------|-------------|
| `pattern_count` | Integer | Total number of patterns |
| `event_type_count` | Integer | Unique abstract event types |
| `total_matches` | Integer | Sum of all pattern frequencies |
| `root_cause_types` | List[String] | All root cause types |

**Analysis:**

1. **Aggregation Functions:**

   - `count(DISTINCT)`: Count unique nodes
   - `sum()`: Sum numeric property
   - `collect(DISTINCT)`: Aggregate into list

2. **Performance:**

   - Full table scan (no WHERE clause)
   - Execution: 50-200ms for 100 patterns
   - Cacheable: Update every 5-10 minutes

3. **Use Cases:**
   - Dashboard statistics
   - Pattern library health check
   - Capacity planning

**Example Output:**

```json
{
  "pattern_count": 47,
  "event_type_count": 23,
  "total_matches": 1842,
  "root_cause_types": [
    "OOM_KILL",
    "CONFIG_CHANGE",
    "DEPLOYMENT",
    "RESOURCE_EXHAUSTION",
    "NETWORK_ERROR",
    "HEALTH_CHECK_FAILED",
    "NODE_FAILURE",
    "STORAGE_ISSUE",
    "API_ERROR",
    "DATABASE_TIMEOUT"
  ]
}
```

**Dashboard Display:**

```python
stats = pattern_store.get_statistics()

print("=== Pattern Library Statistics ===")
print(f"Total Patterns: {stats['pattern_count']}")
print(f"Unique Event Types: {stats['event_type_count']}")
print(f"Total Matches: {stats['total_matches']}")
print(f"Avg Matches per Pattern: {stats['total_matches'] / stats['pattern_count']:.1f}")
print(f"\nRoot Cause Types ({len(stats['root_cause_types'])}):")
for rc_type in stats['root_cause_types']:
    print(f"  - {rc_type}")
```

---

## Topology Queries

### Query 9: Get Service Dependencies

**Purpose:** Retrieve service dependency graph for blast radius calculation.

**Query:**

```cypher
MATCH (source:Resource {kind: "Service", client_id: $client_id})
OPTIONAL MATCH (source)-[:CALLS]->(target:Resource {kind: "Service"})
RETURN source.name as source_service,
       collect(target.name) as dependent_services
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `client_id` | String | Client identifier | `"prod-cluster-1"` |

**Returns:** Service name → list of dependent services

**Analysis:**

- Used for building service dependency graph
- Supports blast radius calculation
- Typical cardinality: 10-100 services per cluster

---

### Query 10: Get Downstream Services (Blast Radius)

**Purpose:** Find all services affected if source service fails.

**Query:**

```cypher
MATCH path = (source:Resource {kind: "Service", name: $service_name})
             -[:CALLS*1..5]->(downstream:Resource {kind: "Service"})
WHERE source.client_id = $client_id
RETURN downstream.name as affected_service,
       length(path) as hops,
       [node in nodes(path) | node.name] as propagation_path
ORDER BY hops
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `service_name` | String | Source service | `"api-gateway"` |
| `client_id` | String | Client identifier | `"prod-cluster-1"` |

**Returns:**

- `affected_service`: Downstream service name
- `hops`: Distance from source (1-5)
- `propagation_path`: Full path from source to target

**Analysis:**

1. **Variable-Length Path:**

   - `[:CALLS*1..5]` matches paths of length 1 to 5
   - Prevents infinite loops in cyclic graphs
   - Max depth of 5 hops is reasonable for most architectures

2. **Performance:**

   - Execution: 20-100ms (depends on graph density)
   - Result count: Typically 5-30 downstream services
   - Complexity: O(b^d) where b=branching factor, d=depth

3. **Blast Radius Interpretation:**
   - 1 hop: Direct dependencies (high impact)
   - 2 hops: Secondary dependencies (medium impact)
   - 3+ hops: Tertiary dependencies (low-medium impact)
   - 5+ hops: Distant dependencies (low impact)

**Example Usage:**

```python
affected = session.run(
    downstream_query,
    service_name="api-gateway",
    client_id="prod-cluster-1"
)

print("Blast Radius Analysis:")
for record in affected:
    service = record['affected_service']
    hops = record['hops']
    path = " → ".join(record['propagation_path'])

    impact = "HIGH" if hops == 1 else "MEDIUM" if hops == 2 else "LOW"
    print(f"  {impact}: {service} ({hops} hops)")
    print(f"    Path: {path}")

# Output:
# Blast Radius Analysis:
#   HIGH: user-service (1 hops)
#     Path: api-gateway → user-service
#   HIGH: auth-service (1 hops)
#     Path: api-gateway → auth-service
#   MEDIUM: payment-service (2 hops)
#     Path: api-gateway → user-service → payment-service
#   LOW: notification-service (3 hops)
#     Path: api-gateway → user-service → payment-service → notification-service
```

---

### Query 11: Get Upstream Services (Root Cause Candidates)

**Purpose:** Find all services that could cause failure in target service.

**Query:**

```cypher
MATCH path = (upstream:Resource {kind: "Service"})
             -[:CALLS*1..5]->(target:Resource {kind: "Service", name: $service_name})
WHERE target.client_id = $client_id
RETURN upstream.name as potential_cause_service,
       length(path) as hops,
       [node in nodes(path) | node.name] as propagation_path
ORDER BY hops
```

**Parameters:**
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `service_name` | String | Target service (symptom) | `"user-service"` |
| `client_id` | String | Client identifier | `"prod-cluster-1"` |

**Returns:**

- `potential_cause_service`: Upstream service name
- `hops`: Distance from upstream to target
- `propagation_path`: Path from upstream to target

**Analysis:**

1. **Root Cause Likelihood:**

   - 1 hop upstream: High likelihood (direct dependency)
   - 2 hops upstream: Medium likelihood
   - 3+ hops upstream: Lower likelihood

2. **Combined with RCA:**

   ```python
   # Get upstream services
   upstream_services = get_upstream_services("user-service")

   # Filter RCA candidates by upstream services
   root_cause_candidates = [
       event for event in all_events
       if event.service in upstream_services
   ]
   ```

**Example:**

```cypher
// user-service is failing, find potential upstream causes
MATCH path = (upstream:Resource {kind: "Service"})
             -[:CALLS*1..3]->(target:Resource {kind: "Service", name: "user-service"})
RETURN upstream.name, length(path) as distance
ORDER BY distance

// Results:
// api-gateway: 1 (direct caller)
// load-balancer: 2 (calls api-gateway → user-service)
```

---

## Schema & Index Queries

### Query 12: View Schema

**Query:**

```cypher
CALL db.schema.visualization()
```

**Returns:** Visual representation of node labels, relationship types, and properties.

---

### Query 13: List Indexes

**Query:**

```cypher
SHOW INDEXES
```

**Example Output:**

```
| name                           | type       | entityType | labelsOrTypes        | properties           | uniqueness |
|--------------------------------|------------|------------|----------------------|----------------------|------------|
| failure_pattern_id             | BTREE      | NODE       | [FailurePattern]     | [pattern_id]         | UNIQUE     |
| abstract_event_signature       | BTREE      | NODE       | [AbstractEvent]      | [signature]          | UNIQUE     |
| failure_pattern_root_cause     | BTREE      | NODE       | [FailurePattern]     | [root_cause_type]    | NONUNIQUE  |
| failure_pattern_frequency      | BTREE      | NODE       | [FailurePattern]     | [frequency]          | NONUNIQUE  |
| episodic_event_time            | BTREE      | NODE       | [Episodic]           | [event_time]         | NONUNIQUE  |
| episodic_client_time           | BTREE      | NODE       | [Episodic]           | [client_id, event_time] | NONUNIQUE  |
```

---

### Query 14: List Constraints

**Query:**

```cypher
SHOW CONSTRAINTS
```

**Example Output:**

```
| name                     | type       | entityType | labelsOrTypes    | properties    |
|--------------------------|------------|------------|------------------|---------------|
| failure_pattern_id       | UNIQUENESS | NODE       | [FailurePattern] | [pattern_id]  |
| abstract_event_signature | UNIQUENESS | NODE       | [AbstractEvent]  | [signature]   |
```

---

### Query 15: Node Count by Label

**Query:**

```cypher
MATCH (n)
RETURN labels(n)[0] as label, count(*) as count
ORDER BY count DESC
```

**Example Output:**

```
| label            | count |
|------------------|-------|
| Episodic         | 12847 |
| Resource         | 3421  |
| FailurePattern   | 47    |
| AbstractEvent    | 23    |
| Incident         | 156   |
```

---

### Query 16: Relationship Count by Type

**Query:**

```cypher
MATCH ()-[r]->()
RETURN type(r) as relationship_type, count(*) as count
ORDER BY count DESC
```

**Example Output:**

```
| relationship_type | count |
|-------------------|-------|
| ABOUT             | 12847 |
| POTENTIAL_CAUSE   | 8932  |
| SELECTS           | 421   |
| PART_OF           | 1234  |
| CONTAINS_EVENT    | 94    |
| CAUSES            | 78    |
| RUNS_ON           | 512   |
| CONTROLS          | 89    |
```

---

## Query Analysis & Performance

### Performance Benchmarks

**Hardware:** 4 vCPU, 16GB RAM, SSD storage

| Query                              | Avg Execution Time | Result Count | Notes                |
| ---------------------------------- | ------------------ | ------------ | -------------------- |
| RCA Event Retrieval (30min window) | 120ms              | 150 events   | With indexes         |
| Get Pattern by ID                  | 15ms               | 1 pattern    | Unique constraint    |
| Get All Patterns                   | 350ms              | 47 patterns  | Full scan            |
| Search by Root Cause               | 45ms               | 8 patterns   | Index lookup         |
| Update Pattern Frequency           | 8ms                | 1 update     | Atomic increment     |
| Pattern Statistics                 | 180ms              | 1 result     | Aggregation          |
| Downstream Services (5 hops)       | 75ms               | 12 services  | Variable-length path |
| Upstream Services (5 hops)         | 60ms               | 8 services   | Variable-length path |

### Query Optimization Checklist

- ✅ **Indexes on filter properties** - `event_time`, `client_id`, `pattern_id`
- ✅ **Composite indexes for common filters** - `(client_id, event_time)`
- ✅ **Unique constraints for lookup keys** - `pattern_id`, `signature`
- ✅ **LIMIT clauses for large result sets** - Prevent OOM
- ✅ **Parameterized queries** - Query plan caching
- ✅ **Batch operations** - Reduce network roundtrips
- ✅ **OPTIONAL MATCH instead of multiple queries** - Reduce latency
- ✅ **collect(DISTINCT) for deduplication** - Prevent duplicate relationships

### Common Performance Issues

#### Issue 1: Slow RCA Query without Time Filter

```cypher
// BAD: No time filter
MATCH (e:Episodic {client_id: $client_id})
RETURN e
// Result: 10-30s for 100k+ events

// GOOD: With time filter
MATCH (e:Episodic)
WHERE e.client_id = $client_id
  AND e.event_time > datetime($cutoff_time)
RETURN e
// Result: 50-200ms for 150 events
```

#### Issue 2: N+1 Query Problem

```python
# BAD: N+1 queries
for pattern_id in pattern_ids:
    pattern = get_pattern_by_id(pattern_id)  # 1 query per pattern

# GOOD: Single query with IN clause
patterns = get_patterns_by_ids(pattern_ids)  # 1 query total
```

#### Issue 3: Large collect() Result

```cypher
// BAD: Collecting all causes (may be 1000s)
MATCH (e:Episodic)
OPTIONAL MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(e)
RETURN e, collect(cause)

// GOOD: Limit collected causes
MATCH (e:Episodic)
OPTIONAL MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(e)
WITH e, cause
ORDER BY cause.event_time DESC
LIMIT 10
RETURN e, collect(cause)
```

### Monitoring Queries

#### Query 17: Slow Query Detection

```cypher
// Enable query logging (neo4j.conf)
// dbms.logs.query.enabled=true
// dbms.logs.query.threshold=100ms

// View slow queries
:queries
```

#### Query 18: Database Size

```cypher
CALL apoc.meta.stats() YIELD nodeCount, relCount, labelCount, propertyKeyCount
RETURN nodeCount, relCount, labelCount, propertyKeyCount
```

---

## Summary

This reference guide covers:

1. ✅ **RCA Queries** - Comprehensive event retrieval with causality and topology
2. ✅ **Pattern Storage** - FEKG storage with schema initialization
3. ✅ **Pattern Retrieval** - Get by ID, get all, search by root cause, statistics
4. ✅ **Topology Queries** - Service dependencies, blast radius, upstream analysis
5. ✅ **Schema Queries** - Indexes, constraints, node/relationship counts
6. ✅ **Performance Analysis** - Benchmarks, optimization tips, common issues

**Key Metrics:**

- **Query Latency**: 10-200ms typical, 500ms+ for complex graph traversals
- **Pattern Library Size**: 50-500 patterns typical
- **Event Throughput**: 100-1000 events/min
- **Index Speedup**: 10-100x for filtered queries

**Best Practices:**

- Always use time window filters for event queries
- Batch pattern storage operations
- Cache pattern library in memory (refresh every 5-10min)
- Monitor slow queries (>100ms threshold)
- Use EXPLAIN/PROFILE for query optimization

For implementation details, see source files in `/mini-server-prod/kgroot-services/`.
