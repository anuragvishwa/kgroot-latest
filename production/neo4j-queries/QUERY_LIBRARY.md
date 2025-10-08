# Neo4j Query Library for Knowledge Graph RCA System

## Table of Contents
1. [RCA & Causality Queries](#rca--causality-queries)
2. [Vector Embedding Queries](#vector-embedding-queries)
3. [Resource & Topology Queries](#resource--topology-queries)
4. [Incident Analysis Queries](#incident-analysis-queries)
5. [Anomaly Detection Queries](#anomaly-detection-queries)
6. [Performance & Health Queries](#performance--health-queries)
7. [Maintenance Queries](#maintenance-queries)

---

## 1. RCA & Causality Queries

### 1.1 Find Root Causes with Confidence Scoring

```cypher
// Find potential root causes for an event with confidence scores
MATCH (e:Episodic {eid: $event_id})-[:ABOUT]->(r:Resource)

// Find causal paths
MATCH (c:Episodic)-[:ABOUT]->(u:Resource)
WHERE c.event_time <= e.event_time
  AND c.event_time >= e.event_time - duration({minutes: $window_minutes})
  AND u <> r

// Find shortest paths in topology
OPTIONAL MATCH p = shortestPath((u)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r))
WHERE p IS NOT NULL

// Calculate confidence scores
WITH e, c, p,
     // Temporal score
     1.0 - (duration.between(c.event_time, e.event_time).milliseconds / (60000.0 * $window_minutes)) AS temporal_score,
     // Distance score
     1.0 / (length(p) + 1.0) AS distance_score,
     // Domain score (K8s-specific patterns)
     CASE
       WHEN c.reason CONTAINS 'OOMKilled' AND e.reason CONTAINS 'CrashLoop' THEN 0.95
       WHEN c.reason CONTAINS 'ImagePull' AND e.reason CONTAINS 'FailedScheduling' THEN 0.90
       WHEN c.reason CONTAINS 'NodeNotReady' AND e.reason CONTAINS 'Evicted' THEN 0.90
       WHEN c.message =~ '(?i).*(connection refused|timeout).*' AND e.severity = 'ERROR' THEN 0.70
       WHEN c.severity = 'ERROR' AND e.severity = 'ERROR' THEN 0.50
       ELSE 0.40
     END AS domain_score

// Final confidence = weighted average
WITH e, c, p,
     (temporal_score * 0.3 + distance_score * 0.3 + domain_score * 0.4) AS confidence,
     temporal_score, distance_score, domain_score

WHERE confidence >= $min_confidence

RETURN
    c.eid AS cause_event_id,
    c.event_time AS cause_time,
    c.reason AS cause_reason,
    c.message AS cause_message,
    c.severity AS cause_severity,
    confidence,
    temporal_score,
    distance_score,
    domain_score,
    length(p) AS hops
ORDER BY confidence DESC
LIMIT $top_k
```

**Parameters**:
```json
{
  "event_id": "evt-abc123",
  "window_minutes": 15,
  "min_confidence": 0.5,
  "top_k": 10
}
```

---

### 1.2 Complete Causal Chain Analysis

```cypher
// Find complete causal chain from root cause to effect
MATCH (effect:Episodic {eid: $event_id})

// Find all ancestors (potential root causes)
MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..5]->(effect)
WHERE NOT EXISTS { (:Episodic)-[:POTENTIAL_CAUSE]->(root) }

// Extract path details
WITH path, effect, root,
     [node IN nodes(path) | {
         eid: node.eid,
         reason: node.reason,
         severity: node.severity,
         event_time: toString(node.event_time)
     }] AS event_chain,
     [rel IN relationships(path) | rel.confidence] AS confidence_chain,
     length(path) AS chain_length

// Calculate overall confidence
WITH path, event_chain, confidence_chain, chain_length,
     reduce(product = 1.0, conf IN confidence_chain | product * conf) AS overall_confidence

WHERE overall_confidence >= $min_overall_confidence

RETURN
    event_chain,
    confidence_chain,
    chain_length,
    overall_confidence
ORDER BY overall_confidence DESC, chain_length ASC
LIMIT 5
```

---

### 1.3 Find Cascading Failures

```cypher
// Detect cascading failure patterns
MATCH (trigger:Episodic)-[:ABOUT]->(r:Resource)
WHERE trigger.event_time >= datetime() - duration({hours: $hours})
  AND trigger.severity IN ['ERROR', 'FATAL']

// Find cascade: events that happened shortly after
MATCH (trigger)-[:POTENTIAL_CAUSE]->(cascade:Episodic)-[:ABOUT]->(affected:Resource)
WHERE cascade.event_time > trigger.event_time
  AND cascade.event_time <= trigger.event_time + duration({minutes: 15})

// Count cascade size
WITH trigger, r, count(DISTINCT cascade) AS cascade_count,
     collect(DISTINCT {
         eid: cascade.eid,
         reason: cascade.reason,
         resource: affected.rid
     }) AS cascaded_events

WHERE cascade_count >= 3

RETURN
    trigger.eid AS trigger_event,
    trigger.reason AS trigger_reason,
    r.rid AS trigger_resource,
    cascade_count,
    cascaded_events
ORDER BY cascade_count DESC
LIMIT 10
```

---

## 2. Vector Embedding Queries

### 2.1 Semantic Similarity Search

```cypher
// Find similar events using vector embeddings
MATCH (e:Episodic)
WHERE e.embedding IS NOT NULL

// Calculate cosine similarity
WITH e,
     gds.similarity.cosine(e.embedding, $query_vector) AS similarity
WHERE similarity >= $min_similarity

// Get event details
MATCH (e)-[:ABOUT]->(r:Resource)

// Get potential causes
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)

// Get incident
OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident)

RETURN
    e.eid AS event_id,
    e.reason AS reason,
    e.message AS message,
    e.severity AS severity,
    toString(e.event_time) AS event_time,
    r.rid AS resource_id,
    r.kind AS resource_kind,
    r.name AS resource_name,
    similarity,
    collect(DISTINCT cause.eid) AS root_causes,
    inc.resource_id AS incident_id
ORDER BY similarity DESC
LIMIT $top_k
```

**Usage**:
```python
# Generate query embedding first
query = "memory leak causing pod crashes"
query_vector = embedding_service.encode(query)

# Run query
result = neo4j_session.run(cypher, {
    "query_vector": query_vector.tolist(),
    "min_similarity": 0.6,
    "top_k": 10
})
```

---

### 2.2 Batch Generate Embeddings

```cypher
// Find events without embeddings
MATCH (e:Episodic)
WHERE e.embedding IS NULL
  AND e.event_time >= datetime() - duration({days: 7})
RETURN
    e.eid AS eid,
    e.reason AS reason,
    e.message AS message
LIMIT $batch_size
```

Then update:
```cypher
// Update embeddings in batch
UNWIND $updates AS update
MATCH (e:Episodic {eid: update.eid})
SET e.embedding = update.embedding,
    e.embedding_model = $model_name,
    e.embedding_updated_at = datetime()
```

---

### 2.3 Find Duplicate/Similar Events

```cypher
// Find duplicate events using embeddings
MATCH (e1:Episodic)
WHERE e1.embedding IS NOT NULL
  AND e1.event_time >= datetime() - duration({hours: 24})

MATCH (e2:Episodic)
WHERE e2.embedding IS NOT NULL
  AND e2.eid <> e1.eid
  AND e2.event_time >= datetime() - duration({hours: 24})

WITH e1, e2,
     gds.similarity.cosine(e1.embedding, e2.embedding) AS similarity
WHERE similarity >= 0.95  // Very high similarity = likely duplicate

RETURN
    e1.eid AS event1,
    e2.eid AS event2,
    e1.reason AS reason1,
    e2.reason AS reason2,
    similarity
ORDER BY similarity DESC
LIMIT 100
```

---

## 3. Resource & Topology Queries

### 3.1 Get Complete Resource Topology

```cypher
// Get complete topology graph for a resource
MATCH (r:Resource {uid: $resource_uid})

// Get all relationships (up to 2 hops)
OPTIONAL MATCH (r)-[rel1]->(related1:Resource)
OPTIONAL MATCH (r)<-[rel2]-(related2:Resource)
OPTIONAL MATCH (related1)-[rel3]->(related3:Resource)

WITH r,
     collect(DISTINCT {
         from: r.rid,
         to: related1.rid,
         type: type(rel1),
         direction: 'outgoing'
     }) AS outgoing,
     collect(DISTINCT {
         from: related2.rid,
         to: r.rid,
         type: type(rel2),
         direction: 'incoming'
     }) AS incoming,
     collect(DISTINCT {
         from: related1.rid,
         to: related3.rid,
         type: type(rel3),
         direction: 'extended'
     }) AS extended

RETURN
    r.rid AS resource,
    r.kind AS kind,
    r.name AS name,
    r.ns AS namespace,
    outgoing + incoming + extended AS relationships
```

---

### 3.2 Find Blast Radius

```cypher
// Calculate blast radius for a failed resource
MATCH (failed:Resource {uid: $resource_uid})

// Find all resources within N hops
MATCH path = (failed)-[:SELECTS|RUNS_ON|CONTROLS*1..$max_hops]-(affected:Resource)

// Get event counts for affected resources
OPTIONAL MATCH (affected)<-[:ABOUT]-(e:Episodic)
WHERE e.event_time >= datetime() - duration({hours: 24})
  AND e.severity IN ['ERROR', 'FATAL']

WITH DISTINCT affected, count(e) AS error_count, length(path) AS distance
ORDER BY distance, error_count DESC

RETURN
    affected.rid AS resource_id,
    affected.kind AS kind,
    affected.name AS name,
    affected.ns AS namespace,
    distance,
    error_count,
    CASE
        WHEN error_count > 10 THEN 'critical'
        WHEN error_count > 5 THEN 'high'
        WHEN error_count > 0 THEN 'medium'
        ELSE 'low'
    END AS impact
```

---

### 3.3 Find Orphaned Resources

```cypher
// Find resources with no relationships
MATCH (r:Resource)
WHERE NOT EXISTS { (r)-[:SELECTS|RUNS_ON|CONTROLS]-() }
  AND r.updated_at < datetime() - duration({hours: 24})
RETURN
    r.rid AS resource_id,
    r.kind AS kind,
    r.name AS name,
    toString(r.updated_at) AS last_updated
ORDER BY r.updated_at ASC
LIMIT 100
```

---

## 4. Incident Analysis Queries

### 4.1 Cluster Related Events into Incidents

```cypher
// Create incidents from clustered events
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE e.event_time >= datetime() - duration({minutes: $window})
  AND e.severity IN ['ERROR', 'FATAL']
  AND NOT EXISTS { (e)-[:PART_OF]->(:Incident) }

// Find related events on same resource
WITH r, collect(e) AS related_events
WHERE size(related_events) >= 3

// Create or merge incident
MERGE (inc:Incident {
    resource_id: r.rid,
    window_start: datetime() - duration({minutes: $window})
})
SET inc.window_end = datetime(),
    inc.event_count = size(related_events),
    inc.severity = CASE
        WHEN ANY(e IN related_events WHERE e.severity = 'FATAL') THEN 'FATAL'
        ELSE 'ERROR'
    END,
    inc.updated_at = datetime()

// Link events to incident
WITH inc, related_events
UNWIND related_events AS event
MERGE (event)-[:PART_OF]->(inc)

RETURN inc.resource_id, inc.event_count
```

---

### 4.2 Get Incident Timeline

```cypher
// Get complete timeline for an incident
MATCH (inc:Incident {resource_id: $resource_id})
MATCH (e:Episodic)-[:PART_OF]->(inc)
MATCH (e)-[:ABOUT]->(r:Resource)

// Get root causes
OPTIONAL MATCH (cause:Episodic)-[pc:POTENTIAL_CAUSE]->(e)
WHERE NOT EXISTS { (:Episodic)-[:POTENTIAL_CAUSE]->(cause) }

WITH inc, e, r, collect(DISTINCT cause) AS root_causes
ORDER BY e.event_time ASC

RETURN
    inc.resource_id AS incident_id,
    toString(inc.window_start) AS start_time,
    toString(inc.window_end) AS end_time,
    inc.event_count AS total_events,
    collect({
        event_id: e.eid,
        event_time: toString(e.event_time),
        reason: e.reason,
        severity: e.severity,
        message: e.message,
        resource: r.rid
    }) AS timeline,
    [cause IN root_causes | {
        eid: cause.eid,
        reason: cause.reason,
        event_time: toString(cause.event_time)
    }] AS root_causes
```

---

### 4.3 Get Most Impactful Incidents

```cypher
// Find incidents with highest impact (most events, longest duration)
MATCH (inc:Incident)
WHERE inc.window_start >= datetime() - duration({days: 7})

MATCH (inc)<-[:PART_OF]-(e:Episodic)

WITH inc,
     count(e) AS event_count,
     duration.between(inc.window_start, inc.window_end).minutes AS duration_minutes,
     collect(DISTINCT e.severity) AS severities

WITH inc, event_count, duration_minutes, severities,
     CASE
         WHEN 'FATAL' IN severities THEN 10
         WHEN 'ERROR' IN severities THEN 5
         ELSE 1
     END * event_count * (duration_minutes / 60.0) AS impact_score

ORDER BY impact_score DESC

RETURN
    inc.resource_id AS incident_id,
    toString(inc.window_start) AS start_time,
    event_count,
    duration_minutes,
    inc.severity AS severity,
    impact_score
LIMIT 10
```

---

## 5. Anomaly Detection Queries

### 5.1 Detect Error Spikes

```cypher
// Compare current error rate to historical average
WITH datetime() - duration({minutes: 15}) AS recent_window,
     datetime() - duration({hours: 24}) AS baseline_window

// Recent error count
MATCH (recent:Episodic)
WHERE recent.event_time >= recent_window
  AND recent.severity IN ['ERROR', 'FATAL']
WITH count(recent) AS recent_count, baseline_window

// Historical average
MATCH (historical:Episodic)
WHERE historical.event_time >= baseline_window
  AND historical.severity IN ['ERROR', 'FATAL']
WITH recent_count, count(historical) / 96.0 AS baseline_avg  // 96 = 24h / 15min

WITH recent_count, baseline_avg,
     recent_count / CASE WHEN baseline_avg > 0 THEN baseline_avg ELSE 1 END AS spike_ratio

WHERE spike_ratio >= 3.0  // 3x normal

RETURN
    recent_count AS current_errors,
    baseline_avg AS average_errors,
    spike_ratio,
    CASE
        WHEN spike_ratio >= 5 THEN 'critical'
        WHEN spike_ratio >= 3 THEN 'high'
        ELSE 'medium'
    END AS severity
```

---

### 5.2 Detect Memory Leak Patterns

```cypher
// Find resources with increasing OOM events
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE e.reason IN ['OOMKilled', 'LOG_OOM_KILLED']
  AND e.event_time >= datetime() - duration({hours: 6})

WITH r, count(e) AS oom_count,
     collect(e.event_time) AS oom_times
WHERE oom_count >= 3

// Check if frequency is increasing (time between events decreasing)
WITH r, oom_count, oom_times,
     [i IN range(0, size(oom_times)-2) |
         duration.between(oom_times[i], oom_times[i+1]).minutes
     ] AS intervals

WITH r, oom_count, intervals,
     CASE
         WHEN size(intervals) >= 2 AND intervals[-1] < intervals[0] THEN true
         ELSE false
     END AS is_accelerating

WHERE is_accelerating

RETURN
    r.rid AS resource_id,
    r.kind AS kind,
    r.name AS name,
    oom_count,
    intervals,
    'Memory leak suspected: OOM frequency increasing' AS diagnosis
```

---

### 5.3 Detect Cascading Failure Patterns

```cypher
// Identify cascading failure patterns
MATCH (trigger:Episodic)-[:ABOUT]->(r1:Resource)
WHERE trigger.event_time >= datetime() - duration({minutes: 30})
  AND trigger.severity IN ['ERROR', 'FATAL']

// Find subsequent failures
MATCH (trigger)-[:POTENTIAL_CAUSE*1..3]->(cascade:Episodic)-[:ABOUT]->(r2:Resource)
WHERE cascade.event_time > trigger.event_time
  AND cascade.event_time <= trigger.event_time + duration({minutes: 15})

WITH trigger, r1, count(DISTINCT cascade) AS cascade_count,
     count(DISTINCT r2) AS affected_resources

WHERE cascade_count >= 5

RETURN
    trigger.eid AS trigger_event,
    trigger.reason AS reason,
    r1.rid AS origin_resource,
    cascade_count AS cascaded_events,
    affected_resources,
    'Cascading failure detected' AS alert_type
ORDER BY cascade_count DESC
```

---

### 5.4 Detect Resource Churn

```cypher
// Detect excessive resource create/delete cycles
MATCH (r:Resource)
WHERE r.kind IN ['Pod', 'Service']

WITH r.kind AS kind, r.ns AS namespace,
     count(*) AS resource_count

WITH kind, namespace,
     resource_count,
     datetime() - duration({hours: 1}) AS window_start

// Count state changes in last hour
MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
WHERE r.kind = kind
  AND r.ns = namespace
  AND e.event_time >= window_start
  AND e.reason IN ['Created', 'Deleted', 'FailedScheduling']

WITH kind, namespace, resource_count,
     count(e) AS state_changes

WHERE state_changes > resource_count * 3  // More than 3x churn

RETURN
    kind,
    namespace,
    resource_count,
    state_changes,
    state_changes / toFloat(resource_count) AS churn_ratio,
    'High resource churn detected' AS alert_type
ORDER BY churn_ratio DESC
```

---

## 6. Performance & Health Queries

### 6.1 Get System Health Dashboard

```cypher
// Complete system health overview
MATCH (r:Resource)
WITH count(r) AS total_resources,
     count(DISTINCT r.kind) AS resource_types,
     count(DISTINCT r.ns) AS namespaces

MATCH (e:Episodic)
WHERE e.event_time >= datetime() - duration({hours: 24})
WITH total_resources, resource_types, namespaces,
     count(e) AS total_events_24h,
     sum(CASE WHEN e.severity = 'ERROR' THEN 1 ELSE 0 END) AS errors_24h,
     sum(CASE WHEN e.severity = 'FATAL' THEN 1 ELSE 0 END) AS fatal_24h

MATCH (inc:Incident)
WHERE inc.window_start >= datetime() - duration({hours: 24})
WITH *, count(inc) AS incidents_24h,
     sum(CASE WHEN NOT EXISTS { (inc)<-[:PART_OF]-() } THEN 1 ELSE 0 END) AS open_incidents

RETURN {
    resources: total_resources,
    resource_types: resource_types,
    namespaces: namespaces,
    events_24h: total_events_24h,
    errors_24h: errors_24h,
    fatal_24h: fatal_24h,
    incidents_24h: incidents_24h,
    open_incidents: open_incidents,
    error_rate: toFloat(errors_24h) / total_events_24h,
    health_score: 1.0 - (toFloat(errors_24h + fatal_24h) / total_events_24h)
} AS dashboard
```

---

### 6.2 Get Resource Health Scores

```cypher
// Calculate health scores for all resources
MATCH (r:Resource)
WHERE r.kind IN ['Pod', 'Service', 'Deployment']

// Get recent events
OPTIONAL MATCH (r)<-[:ABOUT]-(e:Episodic)
WHERE e.event_time >= datetime() - duration({hours: 24})

WITH r,
     count(e) AS total_events,
     sum(CASE WHEN e.severity = 'ERROR' THEN 1 ELSE 0 END) AS errors,
     sum(CASE WHEN e.severity = 'FATAL' THEN 1 ELSE 0 END) AS fatal

// Calculate health score (0-1, higher is better)
WITH r, total_events, errors, fatal,
     1.0 - (toFloat(errors) * 0.5 + toFloat(fatal) * 1.0) / CASE WHEN total_events > 0 THEN total_events ELSE 1 END AS health_score

WHERE health_score < 0.8  // Show only degraded resources

RETURN
    r.rid AS resource_id,
    r.kind AS kind,
    r.name AS name,
    r.ns AS namespace,
    total_events,
    errors,
    fatal,
    round(health_score * 100) / 100.0 AS health_score,
    CASE
        WHEN health_score >= 0.9 THEN 'healthy'
        WHEN health_score >= 0.7 THEN 'degraded'
        WHEN health_score >= 0.5 THEN 'unhealthy'
        ELSE 'critical'
    END AS status
ORDER BY health_score ASC
LIMIT 20
```

---

### 6.3 Get Top Error-Prone Resources

```cypher
// Find resources with most errors
MATCH (r:Resource)<-[:ABOUT]-(e:Episodic)
WHERE e.event_time >= datetime() - duration({days: 7})
  AND e.severity IN ['ERROR', 'FATAL']

WITH r, count(e) AS error_count,
     collect(DISTINCT e.reason) AS error_reasons

ORDER BY error_count DESC

RETURN
    r.rid AS resource_id,
    r.kind AS kind,
    r.name AS name,
    r.ns AS namespace,
    error_count,
    error_reasons,
    size(error_reasons) AS unique_error_types
LIMIT 20
```

---

## 7. Maintenance Queries

### 7.1 Cleanup Old Events

```cypher
// Delete events older than retention period
MATCH (e:Episodic)
WHERE e.event_time < datetime() - duration({days: $retention_days})
WITH e LIMIT 1000
DETACH DELETE e
RETURN count(e) AS deleted
```

---

### 7.2 Cleanup Orphaned Incidents

```cypher
// Delete incidents with no linked events
MATCH (inc:Incident)
WHERE NOT EXISTS { (inc)<-[:PART_OF]-() }
DELETE inc
RETURN count(inc) AS deleted
```

---

### 7.3 Get Database Statistics

```cypher
// Get node and relationship counts
MATCH (n)
WITH labels(n) AS labels, count(*) AS count
UNWIND labels AS label
WITH label, sum(count) AS total
ORDER BY total DESC
RETURN
    label AS node_type,
    total AS count

UNION ALL

MATCH ()-[r]->()
WITH type(r) AS rel_type, count(*) AS count
RETURN
    rel_type AS node_type,
    count
ORDER BY count DESC
```

---

### 7.4 Create/Update Indexes

```cypher
// Create all required indexes
CREATE INDEX resource_uid IF NOT EXISTS FOR (r:Resource) ON (r.uid);
CREATE INDEX resource_rid IF NOT EXISTS FOR (r:Resource) ON (r.rid);
CREATE INDEX resource_kind IF NOT EXISTS FOR (r:Resource) ON (r.kind);
CREATE INDEX resource_ns_name IF NOT EXISTS FOR (r:Resource) ON (r.ns, r.name);
CREATE INDEX episodic_eid IF NOT EXISTS FOR (e:Episodic) ON (e.eid);
CREATE INDEX episodic_time IF NOT EXISTS FOR (e:Episodic) ON (e.event_time);
CREATE INDEX episodic_severity IF NOT EXISTS FOR (e:Episodic) ON (e.severity);
CREATE INDEX episodic_reason IF NOT EXISTS FOR (e:Episodic) ON (e.reason);
CREATE INDEX incident_resource IF NOT EXISTS FOR (i:Incident) ON (i.resource_id, i.window_start);

// Create constraints
CREATE CONSTRAINT resource_rid_unique IF NOT EXISTS FOR (r:Resource) REQUIRE r.rid IS UNIQUE;
CREATE CONSTRAINT episodic_eid_unique IF NOT EXISTS FOR (e:Episodic) REQUIRE e.eid IS UNIQUE;

// Show all indexes
SHOW INDEXES;
```

---

## Advanced Queries

### Pattern: Find Common Failure Paths

```cypher
// Find most common failure sequences
MATCH path = (cause:Episodic)-[:POTENTIAL_CAUSE*2..4]->(effect:Episodic)
WHERE cause.event_time >= datetime() - duration({days: 7})

WITH [node IN nodes(path) | node.reason] AS failure_sequence,
     count(*) AS occurrence_count

WHERE occurrence_count >= 5

RETURN
    failure_sequence,
    occurrence_count,
    toFloat(occurrence_count) / 100.0 AS frequency_score
ORDER BY occurrence_count DESC
LIMIT 10
```

---

### Pattern: Find Correlation Between Resource Types

```cypher
// Find which resource types frequently fail together
MATCH (e1:Episodic)-[:ABOUT]->(r1:Resource),
      (e2:Episodic)-[:ABOUT]->(r2:Resource)
WHERE e1.event_time >= datetime() - duration({days: 7})
  AND e2.event_time >= datetime() - duration({days: 7})
  AND e1 <> e2
  AND r1.kind <> r2.kind
  AND abs(duration.between(e1.event_time, e2.event_time).minutes) <= 5
  AND e1.severity IN ['ERROR', 'FATAL']
  AND e2.severity IN ['ERROR', 'FATAL']

WITH r1.kind AS kind1, r2.kind AS kind2,
     count(*) AS co_occurrence
WHERE co_occurrence >= 10

RETURN
    kind1,
    kind2,
    co_occurrence,
    'These resource types frequently fail together' AS insight
ORDER BY co_occurrence DESC
```

---

## Query Performance Tips

1. **Always filter by time first**: `WHERE e.event_time >= datetime() - duration({days: 7})`
2. **Use LIMIT for large result sets**
3. **Use indexes**: Ensure `event_time`, `eid`, `rid`, `uid` are indexed
4. **Avoid cartesian products**: Use proper MATCH patterns
5. **Use EXPLAIN/PROFILE** to optimize queries
6. **Batch updates**: Process 1000-10000 nodes at a time

---

## Query Templates for Common Tasks

### Template: Time-Series Analysis
```cypher
MATCH (e:Episodic)
WHERE e.event_time >= $start_time
  AND e.event_time <= $end_time
  AND e.severity = $severity
WITH duration.inDays($start_time, $end_time).days AS day_count,
     count(e) AS event_count
RETURN day_count, event_count
```

### Template: Aggregation by Time Buckets
```cypher
MATCH (e:Episodic)
WHERE e.event_time >= datetime() - duration({hours: 24})
WITH datetime.truncate('hour', e.event_time) AS hour,
     e.severity AS severity,
     count(*) AS count
RETURN hour, severity, count
ORDER BY hour, severity
```

---

This query library covers all major use cases. Combine and modify these queries as needed for your specific requirements!
